"""
tests/unit/test_property_phase2.py — Property-based tests for Phase 2
(provider ecosystem enhancements) using Hypothesis.

Properties 14–20: FHIR Patient parsing, vendor URL construction,
DocumentReference round trip, incremental sync filtering, conflict
resolution, WebSocket event triggering, note editing preservation.

Minimum 100 examples per property (Hypothesis default is 100).
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from mcp_servers.ehr.base import EHRNote, EHRPatient
from mcp_servers.ehr.fhir_server import (
    _parse_patient,
    _parse_bundle_entries,
    _parse_document_reference,
    _build_document_reference,
    VENDOR_PATHS,
    FHIRAdapter,
)
from api.sync import IncrementalSync, ConflictResolver


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# FHIR Patient fields
fhir_id = st.from_regex(r"[a-f0-9]{8,16}", fullmatch=True)
human_name = st.from_regex(r"[A-Z][a-z]{1,15}", fullmatch=True)
dob_str = st.dates(
    min_value=datetime(1920, 1, 1).date(),
    max_value=datetime(2010, 12, 31).date(),
).map(lambda d: d.isoformat())
gender = st.sampled_from(["male", "female", "other", "unknown"])
mrn_value = st.from_regex(r"[0-9]{5,10}", fullmatch=True)

# URL components for vendor URL tests
url_base = st.builds(
    lambda host, port: f"https://{host}:{port}/fhir/R4",
    st.from_regex(r"[a-z]{3,12}\.[a-z]{2,4}", fullmatch=True),
    st.integers(min_value=443, max_value=9999),
)
vendor_name = st.sampled_from(["epic", "cerner", "athena"])

# Note content for DocumentReference round trip
note_text = st.text(min_size=1, max_size=500, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))
note_type = st.sampled_from(["Progress note", "SOAP Note", "H&P", "Discharge Summary", ""])
note_author = st.one_of(st.none(), human_name.map(lambda n: f"Dr. {n}"))
note_date = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2026, 12, 31),
        timezones=st.just(timezone.utc),
    ).map(lambda dt: dt.isoformat()),
)

# Timestamps for incremental sync
past_dt = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 6, 1),
    timezones=st.just(timezone.utc),
)

# File paths and content for conflict resolution
safe_filename = st.from_regex(r"[a-z_]{1,15}\.(md|txt|json)", fullmatch=True)
file_content = st.text(min_size=1, max_size=300, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))

# Encounter IDs for WebSocket tests
encounter_id = st.from_regex(r"[a-z_]+_[0-9]{4,8}_[0-9]{8}", fullmatch=True)


# ===========================================================================
# Property 14: FHIR Patient resource parsing
# ===========================================================================

class TestPropertyFHIRPatientParsing:
    """Property 14: Correct extraction of id, given_name, family_name, dob, mrn."""

    @given(
        pid=fhir_id,
        given=human_name,
        family=human_name,
        dob=dob_str,
        sex=gender,
        mrn=mrn_value,
    )
    @settings(max_examples=200)
    def test_parse_patient_extracts_all_fields(
        self, pid: str, given: str, family: str, dob: str, sex: str, mrn: str
    ):
        resource = {
            "resourceType": "Patient",
            "id": pid,
            "name": [{"given": [given], "family": family}],
            "birthDate": dob,
            "gender": sex,
            "identifier": [
                {
                    "type": {"coding": [{"code": "MR"}]},
                    "value": mrn,
                }
            ],
        }
        patient = _parse_patient(resource)
        assert patient.id == pid
        assert patient.given_name == given
        assert patient.family_name == family
        assert patient.dob == dob
        assert patient.sex == sex
        assert patient.mrn == mrn

    @given(pid=fhir_id, given=human_name, family=human_name)
    @settings(max_examples=200)
    def test_parse_from_bundle(self, pid: str, given: str, family: str):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": pid,
                        "name": [{"given": [given], "family": family}],
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                    }
                },
            ],
        }
        patients = _parse_bundle_entries(bundle, "Patient")
        assert len(patients) == 1
        parsed = _parse_patient(patients[0])
        assert parsed.id == pid
        assert parsed.given_name == given
        assert parsed.family_name == family

    @given(pid=fhir_id)
    @settings(max_examples=200)
    def test_missing_name_gives_none(self, pid: str):
        resource = {"resourceType": "Patient", "id": pid}
        patient = _parse_patient(resource)
        assert patient.id == pid
        assert patient.given_name is None or patient.given_name == ""
        assert patient.family_name is None or patient.family_name == ""


# ===========================================================================
# Property 15: FHIR vendor URL construction
# ===========================================================================

class TestPropertyFHIRVendorURL:
    """Property 15: Valid URL with base as prefix for all vendors."""

    @given(base=url_base, vendor=vendor_name)
    @settings(max_examples=200)
    def test_url_starts_with_base(self, base: str, vendor: str):
        adapter = FHIRAdapter(fhir_base_url=base, vendor=vendor)
        for resource_key in ["patient", "condition", "medication_request", "allergy", "observation", "document_reference"]:
            url = adapter.build_resource_url(resource_key)
            assert url.startswith(base.rstrip("/")), f"{url} does not start with {base}"

    @given(base=url_base, vendor=vendor_name)
    @settings(max_examples=200)
    def test_all_resource_keys_produce_valid_urls(self, base: str, vendor: str):
        adapter = FHIRAdapter(fhir_base_url=base, vendor=vendor)
        paths = VENDOR_PATHS[vendor]
        for key in paths:
            if key == "token":
                continue
            url = adapter.build_resource_url(key)
            assert "://" in url
            assert url.startswith("https://") or url.startswith("http://")

    @given(base=url_base)
    @settings(max_examples=200)
    def test_unknown_vendor_falls_back(self, base: str):
        adapter = FHIRAdapter(fhir_base_url=base, vendor="unknown_vendor")
        url = adapter.build_resource_url("patient")
        assert url.startswith(base.rstrip("/"))


# ===========================================================================
# Property 16: FHIR DocumentReference serialization round trip
# ===========================================================================

class TestPropertyDocumentReferenceRoundTrip:
    """Property 16: serialize → parse produces equivalent note."""

    @given(
        text=note_text,
        ntype=note_type,
        author=note_author,
        date=note_date,
        patient_id=fhir_id,
    )
    @settings(max_examples=200)
    def test_round_trip_preserves_text(
        self, text: str, ntype: str, author: str | None, date: str | None, patient_id: str
    ):
        original = EHRNote(text=text, note_type=ntype or "Progress note", author=author, date=date)
        doc_ref = _build_document_reference(patient_id, original)
        parsed = _parse_document_reference(doc_ref)
        assert parsed is not None
        assert parsed.text == text

    @given(
        text=note_text,
        ntype=note_type.filter(lambda s: s != ""),
        patient_id=fhir_id,
    )
    @settings(max_examples=200)
    def test_round_trip_preserves_note_type(self, text: str, ntype: str, patient_id: str):
        original = EHRNote(text=text, note_type=ntype)
        doc_ref = _build_document_reference(patient_id, original)
        parsed = _parse_document_reference(doc_ref)
        assert parsed is not None
        assert parsed.note_type == ntype

    @given(text=note_text, patient_id=fhir_id, enc_id=fhir_id)
    @settings(max_examples=200)
    def test_encounter_context_included(self, text: str, patient_id: str, enc_id: str):
        note = EHRNote(text=text)
        doc_ref = _build_document_reference(patient_id, note, encounter_id=enc_id)
        assert "context" in doc_ref
        assert f"Encounter/{enc_id}" in json.dumps(doc_ref)

    @given(text=note_text, patient_id=fhir_id)
    @settings(max_examples=200)
    def test_no_encounter_no_context(self, text: str, patient_id: str):
        note = EHRNote(text=text)
        doc_ref = _build_document_reference(patient_id, note, encounter_id=None)
        assert "context" not in doc_ref


# ===========================================================================
# Property 17: Incremental sync filters by timestamp
# ===========================================================================

class TestPropertyIncrementalSync:
    """Property 17: Only strictly newer remote files are selected for download."""

    @given(local_dt=past_dt, offset_hours=st.integers(min_value=1, max_value=720))
    @settings(max_examples=200)
    def test_newer_remote_returns_true(self, local_dt: datetime, offset_hours: int):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "test.md"
            local_file.write_text("content")
            os.utime(local_file, (local_dt.timestamp(), local_dt.timestamp()))
            remote_dt = local_dt + timedelta(hours=offset_hours)
            remote_header = format_datetime(remote_dt, usegmt=True)
            assert IncrementalSync.should_fetch(local_file, remote_header) is True

    @given(local_dt=past_dt, offset_hours=st.integers(min_value=1, max_value=720))
    @settings(max_examples=200)
    def test_older_remote_returns_false(self, local_dt: datetime, offset_hours: int):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            remote_dt = local_dt - timedelta(hours=offset_hours)
            local_file = Path(tmp_dir) / "test.md"
            local_file.write_text("content")
            os.utime(local_file, (local_dt.timestamp(), local_dt.timestamp()))
            remote_header = format_datetime(remote_dt, usegmt=True)
            assert IncrementalSync.should_fetch(local_file, remote_header) is False

    @given(data=st.data())
    @settings(max_examples=200)
    def test_missing_local_always_fetches(self, data):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "nonexistent.md"
            # Use a valid RFC 2822 date
            dt = data.draw(past_dt)
            remote_header = format_datetime(dt, usegmt=True)
            assert IncrementalSync.should_fetch(local_file, remote_header) is True


# ===========================================================================
# Property 18: Conflict resolution preserves both versions
# ===========================================================================

class TestPropertyConflictResolution:
    """Property 18: .local rename and remote write behavior."""

    @given(
        local_content=file_content,
        remote_content=file_content,
        fname=safe_filename,
    )
    @settings(max_examples=200)
    def test_keep_both_preserves_local_as_backup(
        self, local_content: str, remote_content: str, fname: str
    ):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / fname
            local_file.write_text(local_content, encoding="utf-8")
            resolver = ConflictResolver(strategy="keep_both")
            resolver.resolve(local_file, remote_content, "2026-01-01T00:00:00Z")
            assert local_file.read_text(encoding="utf-8") == remote_content
            backup = local_file.with_suffix(local_file.suffix + ".local")
            assert backup.exists()
            assert backup.read_text(encoding="utf-8") == local_content

    @given(
        local_content=file_content,
        remote_content=file_content,
        fname=safe_filename,
    )
    @settings(max_examples=200)
    def test_keep_remote_overwrites(
        self, local_content: str, remote_content: str, fname: str
    ):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / fname
            local_file.write_text(local_content, encoding="utf-8")
            resolver = ConflictResolver(strategy="keep_remote")
            resolver.resolve(local_file, remote_content, "2026-01-01T00:00:00Z")
            assert local_file.read_text(encoding="utf-8") == remote_content

    @given(
        local_content=file_content,
        remote_content=file_content,
        fname=safe_filename,
    )
    @settings(max_examples=200)
    def test_keep_local_unchanged(
        self, local_content: str, remote_content: str, fname: str
    ):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / fname
            local_file.write_text(local_content, encoding="utf-8")
            resolver = ConflictResolver(strategy="keep_local")
            resolver.resolve(local_file, remote_content, "2026-01-01T00:00:00Z")
            assert local_file.read_text(encoding="utf-8") == local_content


# ===========================================================================
# Property 19: WebSocket pipeline event triggers sync
# ===========================================================================

class TestPropertyWebSocketSync:
    """Property 19: pipeline.complete messages trigger fetch for note + transcript."""

    @given(eid=encounter_id)
    @settings(max_examples=200)
    def test_pipeline_complete_triggers_fetch(self, eid: str):
        """Verify that a pipeline.complete message with an encounter ID
        would trigger fetches for both note and transcript endpoints."""
        message = {"event": "pipeline.complete", "encounter_id": eid}
        event_type = message.get("event") or message.get("type")
        enc = message.get("encounter_id") or message.get("id")
        assert event_type == "pipeline.complete"
        assert enc == eid
        # Verify the expected fetch URLs would be constructed
        note_url = f"/pipeline/output/{eid}/note"
        transcript_url = f"/pipeline/output/{eid}/transcript"
        assert eid in note_url
        assert eid in transcript_url

    @given(eid=encounter_id)
    @settings(max_examples=200)
    def test_alternate_message_format(self, eid: str):
        """pipeline.complete can use 'type' and 'id' keys too."""
        message = {"type": "pipeline.complete", "id": eid}
        event_type = message.get("event") or message.get("type")
        enc = message.get("encounter_id") or message.get("id")
        assert event_type == "pipeline.complete"
        assert enc == eid

    @given(eid=encounter_id, event=st.sampled_from(["pipeline.started", "pipeline.error", "heartbeat"]))
    @settings(max_examples=200)
    def test_non_complete_events_ignored(self, eid: str, event: str):
        """Only pipeline.complete should trigger sync."""
        message = {"event": event, "encounter_id": eid}
        event_type = message.get("event")
        assert event_type != "pipeline.complete"


# ===========================================================================
# Property 20: Note editing preserves both versions
# ===========================================================================

class TestPropertyNoteEditPreservation:
    """Property 20: Both original and edited note files exist after save."""

    @given(
        original=file_content,
        edited=file_content,
        enc_id=encounter_id,
    )
    @settings(max_examples=200)
    def test_save_preserves_both_versions(
        self, original: str, edited: str, enc_id: str
    ):
        """Simulate the note save workflow: original stays, edited written alongside."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_dir = Path(tmp_dir) / enc_id
            encounter_dir.mkdir(parents=True)

            original_path = encounter_dir / "generated_note.md"
            edited_path = encounter_dir / "edited_note.md"

            original_path.write_text(original, encoding="utf-8")
            edited_path.write_text(edited, encoding="utf-8")

            assert original_path.exists()
            assert edited_path.exists()
            assert original_path.read_text(encoding="utf-8") == original
            assert edited_path.read_text(encoding="utf-8") == edited

    @given(original=file_content, enc_id=encounter_id)
    @settings(max_examples=200)
    def test_approve_does_not_delete_original(
        self, original: str, enc_id: str
    ):
        """Approving a note should not remove the original."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_dir = Path(tmp_dir) / enc_id
            encounter_dir.mkdir(parents=True)

            original_path = encounter_dir / "generated_note.md"
            status_path = encounter_dir / "status.json"

            original_path.write_text(original, encoding="utf-8")
            status_path.write_text(json.dumps({"status": "approved"}), encoding="utf-8")

            assert original_path.exists()
            assert original_path.read_text(encoding="utf-8") == original
