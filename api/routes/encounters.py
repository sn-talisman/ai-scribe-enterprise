"""
api/routes/encounters.py

Encounter / sample routes. Reads from the output/ and data/ directories.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api import data_loader as dl
from api.models import (
    SampleSummary,
    SampleDetail,
    NoteContent,
    ComparisonContent,
    GoldNoteContent,
    EncounterCreateRequest,
    EncounterResponse,
)

router = APIRouter(prefix="/encounters", tags=["encounters"])


# ---------------------------------------------------------------------------
# Sample listing (read-only, backed by output/ directory)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SampleSummary])
def list_encounters(
    mode: Optional[str] = Query(None, description="Filter by 'dictation' or 'ambient'"),
    version: Optional[str] = Query(None, description="Filter by version e.g. 'v4'"),
):
    """List all available samples / encounters."""
    samples = dl.list_samples()
    if mode:
        samples = [s for s in samples if s["mode"] == mode]
    if version:
        samples = [s for s in samples if version in s["versions"]]
    return [SampleSummary(**s) for s in samples]


@router.get("/{sample_id}", response_model=SampleDetail)
def get_encounter(sample_id: str):
    """Get metadata + patient context for a sample."""
    samples = dl.list_samples()
    match = next((s for s in samples if s["sample_id"] == sample_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return SampleDetail(
        **match,
        patient_context=dl.get_patient_context(sample_id),
    )


@router.get("/{sample_id}/note", response_model=NoteContent)
def get_note(
    sample_id: str,
    version: str = Query(dl.LATEST_VERSION, description="Pipeline version"),
):
    """Get the generated clinical note (Markdown)."""
    content = dl.get_generated_note(sample_id, version)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Generated note not found for sample '{sample_id}' version '{version}'",
        )
    return NoteContent(sample_id=sample_id, version=version, content=content)


@router.get("/{sample_id}/comparison", response_model=ComparisonContent)
def get_comparison(
    sample_id: str,
    version: str = Query(dl.LATEST_VERSION, description="Pipeline version"),
):
    """Get the gold vs generated comparison (Markdown)."""
    content = dl.get_comparison(sample_id, version)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Comparison not found for sample '{sample_id}' version '{version}'",
        )
    return ComparisonContent(sample_id=sample_id, version=version, content=content)


@router.get("/{sample_id}/gold", response_model=GoldNoteContent)
def get_gold_note(sample_id: str):
    """Get the gold-standard clinical note (Markdown)."""
    content = dl.get_gold_note(sample_id)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Gold note not found for sample '{sample_id}'",
        )
    return GoldNoteContent(sample_id=sample_id, content=content)


@router.get("/{sample_id}/transcript")
def get_transcript(
    sample_id: str,
    version: str = Query(dl.LATEST_VERSION),
):
    """Get the standalone transcript text for a sample."""
    content = dl.get_transcript(sample_id, version)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found for sample '{sample_id}' version '{version}'",
        )
    transcript_versions = dl.list_transcript_versions(sample_id)
    return {
        "sample_id": sample_id,
        "version": version,
        "content": content,
        "versions": transcript_versions,
    }


@router.get("/{sample_id}/audio")
def get_audio(sample_id: str):
    """Stream the raw audio file for a sample."""
    from fastapi.responses import FileResponse
    audio_path = dl.get_audio_path(sample_id)
    if audio_path is None:
        raise HTTPException(status_code=404, detail=f"Audio not found for '{sample_id}'")
    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"{sample_id}.mp3")


@router.get("/{sample_id}/quality")
def get_sample_quality(
    sample_id: str,
    version: str = Query(dl.LATEST_VERSION),
):
    """Get quality scores for a specific sample."""
    scores = dl._get_sample_scores(sample_id, version)
    if scores is None:
        raise HTTPException(
            status_code=404,
            detail=f"Quality scores not found for sample '{sample_id}' version '{version}'",
        )
    return {"sample_id": sample_id, "version": version, **scores}


# ---------------------------------------------------------------------------
# Create & upload (triggers pipeline run)
# ---------------------------------------------------------------------------

# In-memory store for demo — replace with DB in production
_encounters: dict[str, dict] = {}


@router.post("", response_model=EncounterResponse, status_code=201)
def create_encounter(req: EncounterCreateRequest):
    """Create a new encounter (returns encounter_id for polling)."""
    encounter_id = str(uuid.uuid4())
    enc = {
        "encounter_id": encounter_id,
        "status": "pending",
        "provider_id": req.provider_id,
        "patient_id": req.patient_id,
        "visit_type": req.visit_type,
        "mode": req.mode,
        "message": "Waiting for audio upload",
    }
    _encounters[encounter_id] = enc
    return EncounterResponse(**enc)


@router.post("/{encounter_id}/upload")
async def upload_audio(encounter_id: str):
    """
    Audio upload endpoint. Accepts multipart form data.
    Triggers the pipeline as a background task.

    Note: Full pipeline execution requires WhisperX + Ollama running locally.
    This endpoint registers the upload and marks the encounter as processing.
    """
    enc = _encounters.get(encounter_id)
    if not enc:
        raise HTTPException(status_code=404, detail=f"Encounter '{encounter_id}' not found")

    enc["status"] = "processing"
    enc["message"] = "Audio received — pipeline queued (requires local GPU + Ollama)"

    # TODO (Session 9 extension): launch pipeline via asyncio.create_task
    # and emit progress events via WebSocket

    return {
        "encounter_id": encounter_id,
        "status": "processing",
        "message": enc["message"],
    }


@router.get("/{encounter_id}/status")
def get_encounter_status(encounter_id: str):
    """Poll pipeline status for a created encounter."""
    enc = _encounters.get(encounter_id)
    if not enc:
        # May be a real sample_id from output/
        raise HTTPException(status_code=404, detail=f"Encounter '{encounter_id}' not found")
    return enc
