"""
Unit tests for the FHIR R4 EHR adapter.

Tests cover:
- FHIR Patient resource parsing (mock FHIR Bundle response)
- FHIR vendor URL construction for epic, cerner, athena
- OAuth2 token refresh logic
- Fallback to stub when FHIR endpoint unreachable
- All adapter methods with mocked FHIR responses
- health_check returns False when endpoint unreachable
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_servers.ehr.base import (
    EHRAllergy,
    EHRLabResult,
    EHRMedication,
    EHRNote,
    EHRPatient,
    EHRProblem,
    PatientIdentifier,
    PushResult,
)
from mcp_servers.ehr.fhir_server import (
    DEFAULT_SCOPES,
    VENDOR_PATHS,
    FHIRAdapter,
    OAuthTokenManager,
    _build_document_reference,
    _parse_allergy,
    _parse_bundle_entries,
    _parse_condition,
    _parse_document_reference,
    _parse_medication_request,
    _parse_observation,
    _parse_patient,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter() -> FHIRAdapter:
    return FHIRAdapter(
        fhir_base_url="https://fhir.example.com/R4",
        vendor="epic",
        client_id="test-client",
        client_secret="test-secret",
    )


@pytest.fixture
def fhir_patient_bundle() -> dict:
    """A minimal FHIR R4 Bundle with one Patient resource."""
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": 1,
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-123",
                    "name": [{"family": "Smith", "given": ["John"]}],
                    "birthDate": "1980-05-15",
                    "gender": "male",
                    "identifier": [
                        {
                            "type": {
                                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]
                            },
                            "value": "MRN-001",
                        }
                    ],
                }
            }
        ],
    }


@pytest.fixture
def fhir_condition_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "M54.5", "display": "Low back pain"}],
                        "text": "Low back pain",
                    },
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "onsetDateTime": "2025-01-10",
                }
            }
        ],
    }


@pytest.fixture
def fhir_medication_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "medicationCodeableConcept": {
                        "coding": [{"code": "197361", "display": "Ibuprofen 400mg"}],
                        "text": "Ibuprofen 400mg",
                    },
                    "status": "active",
                    "dosageInstruction": [
                        {
                            "doseAndRate": [{"doseQuantity": {"value": 400, "unit": "mg"}}],
                            "timing": {"repeat": {"frequency": 3, "period": 1, "periodUnit": "d"}},
                            "route": {"coding": [{"display": "Oral"}]},
                        }
                    ],
                }
            }
        ],
    }


@pytest.fixture
def fhir_allergy_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "code": {
                        "coding": [{"display": "Penicillin"}],
                        "text": "Penicillin",
                    },
                    "reaction": [
                        {
                            "manifestation": [{"coding": [{"display": "Hives"}]}],
                            "severity": "moderate",
                        }
                    ],
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                }
            }
        ],
    }


@pytest.fixture
def fhir_observation_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {
                        "coding": [{"display": "Hemoglobin"}],
                        "text": "Hemoglobin",
                    },
                    "valueQuantity": {"value": 14.2, "unit": "g/dL"},
                    "referenceRange": [{"low": {"value": 12.0}, "high": {"value": 17.5}}],
                    "effectiveDateTime": "2026-02-01",
                    "interpretation": [{"coding": [{"code": "N"}]}],
                }
            }
        ],
    }


@pytest.fixture
def fhir_document_bundle() -> dict:
    note_text = "Patient presents with chronic low back pain."
    encoded = base64.b64encode(note_text.encode()).decode()
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "DocumentReference",
                    "type": {"coding": [{"display": "Progress note"}]},
                    "date": "2026-02-15T10:00:00Z",
                    "author": [{"display": "Dr. Smith"}],
                    "content": [{"attachment": {"contentType": "text/plain", "data": encoded}}],
                }
            }
        ],
    }


# ---------------------------------------------------------------------------
# FHIR Patient resource parsing
# ---------------------------------------------------------------------------

class TestFHIRPatientParsing:
    def test_parse_patient_from_bundle(self, fhir_patient_bundle):
        resources = _parse_bundle_entries(fhir_patient_bundle, "Patient")
        assert len(resources) == 1
        patient = _parse_patient(resources[0])
        assert patient.id == "pat-123"
        assert patient.given_name == "John"
        assert patient.family_name == "Smith"
        assert patient.dob == "1980-05-15"
        assert patient.sex == "male"
        assert patient.mrn == "MRN-001"

    def test_parse_patient_missing_name(self):
        resource = {"resourceType": "Patient", "id": "pat-456", "birthDate": "1990-01-01"}
        patient = _parse_patient(resource)
        assert patient.id == "pat-456"
        assert patient.given_name is None
        assert patient.family_name is None

    def test_parse_patient_no_mrn(self):
        resource = {
            "resourceType": "Patient",
            "id": "pat-789",
            "name": [{"family": "Doe", "given": ["Jane"]}],
            "identifier": [{"value": "some-id"}],
        }
        patient = _parse_patient(resource)
        assert patient.mrn is None

    def test_parse_empty_bundle(self):
        bundle = {"resourceType": "Bundle", "type": "searchset", "entry": []}
        assert _parse_bundle_entries(bundle, "Patient") == []

    def test_parse_bundle_no_entry_key(self):
        bundle = {"resourceType": "Bundle", "type": "searchset"}
        assert _parse_bundle_entries(bundle, "Patient") == []

    def test_parse_bundle_filters_resource_type(self, fhir_patient_bundle):
        assert _parse_bundle_entries(fhir_patient_bundle, "Condition") == []


# ---------------------------------------------------------------------------
# FHIR vendor URL construction
# ---------------------------------------------------------------------------

class TestVendorURLConstruction:
    def test_epic_url(self, adapter):
        url = adapter.build_resource_url("patient", identifier="MRN-001")
        assert url.startswith("https://fhir.example.com/R4")
        assert "/Patient" in url
        assert "identifier=MRN-001" in url

    def test_cerner_url(self):
        a = FHIRAdapter(fhir_base_url="https://fhir.cerner.com/R4", vendor="cerner")
        url = a.build_resource_url("condition", patient="pat-1")
        assert url.startswith("https://fhir.cerner.com/R4")
        assert "/Condition" in url
        assert "patient=pat-1" in url

    def test_athena_url(self):
        a = FHIRAdapter(fhir_base_url="https://fhir.athena.io/R4", vendor="athena")
        url = a.build_resource_url("observation", patient="pat-2", category="laboratory")
        assert url.startswith("https://fhir.athena.io/R4")
        assert "/Observation" in url
        assert "patient=pat-2" in url
        assert "category=laboratory" in url

    def test_all_vendors_have_required_paths(self):
        required = {"token", "patient", "condition", "medication_request", "allergy", "observation", "document_reference"}
        for vendor, paths in VENDOR_PATHS.items():
            assert required.issubset(paths.keys()), f"{vendor} missing paths: {required - paths.keys()}"

    def test_url_no_params(self, adapter):
        url = adapter.build_resource_url("patient")
        assert url == "https://fhir.example.com/R4/Patient"
        assert "?" not in url

    def test_unknown_vendor_falls_back_to_epic(self):
        a = FHIRAdapter(fhir_base_url="https://fhir.unknown.com/R4", vendor="unknown")
        url = a.build_resource_url("patient")
        assert "/Patient" in url


# ---------------------------------------------------------------------------
# OAuth2 token management
# ---------------------------------------------------------------------------

class TestOAuthTokenManager:
    async def test_token_refresh(self):
        mgr = OAuthTokenManager(
            token_url="https://auth.example.com/token",
            client_id="cid",
            client_secret="csecret",
            scopes=["patient/*.read"],
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "tok-abc", "expires_in": 3600}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        token = await mgr.get_token(mock_client)
        assert token == "tok-abc"
        mock_client.post.assert_called_once()

    async def test_token_cached_when_not_expired(self):
        mgr = OAuthTokenManager(
            token_url="https://auth.example.com/token",
            client_id="cid",
            client_secret="csecret",
            scopes=["patient/*.read"],
        )
        mgr._access_token = "cached-token"
        mgr._expires_at = time.time() + 3600

        mock_client = AsyncMock()
        token = await mgr.get_token(mock_client)
        assert token == "cached-token"
        mock_client.post.assert_not_called()

    async def test_token_refreshed_when_expired(self):
        mgr = OAuthTokenManager(
            token_url="https://auth.example.com/token",
            client_id="cid",
            client_secret="csecret",
            scopes=["patient/*.read"],
        )
        mgr._access_token = "old-token"
        mgr._expires_at = time.time() - 10  # expired

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "new-token", "expires_in": 1800}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        token = await mgr.get_token(mock_client)
        assert token == "new-token"

    def test_invalidate_forces_refresh(self):
        mgr = OAuthTokenManager(
            token_url="https://auth.example.com/token",
            client_id="cid",
            client_secret="csecret",
            scopes=[],
        )
        mgr._access_token = "some-token"
        mgr._expires_at = time.time() + 9999
        assert not mgr.is_expired

        mgr.invalidate()
        assert mgr.is_expired
        assert mgr._access_token is None


# ---------------------------------------------------------------------------
# Fallback to stub when FHIR endpoint unreachable
# ---------------------------------------------------------------------------

class TestFallbackToStub:
    async def test_get_patient_falls_back_on_connect_error(self, adapter):
        """When FHIR endpoint is unreachable, adapter falls back to stub."""
        # Force the adapter to use a client that raises ConnectError
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        adapter._client = mock_client

        identifier = PatientIdentifier(mrn="12345")
        patient = await adapter.get_patient(identifier)
        # Stub returns a patient (may have limited data)
        assert isinstance(patient, EHRPatient)

    async def test_get_medications_falls_back_on_timeout(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        adapter._client = mock_client

        meds = await adapter.get_medications("pat-1")
        assert isinstance(meds, list)

    async def test_get_allergies_falls_back_on_connect_error(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        adapter._client = mock_client

        allergies = await adapter.get_allergies("pat-1")
        assert isinstance(allergies, list)

    async def test_push_note_falls_back_on_connect_error(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        adapter._client = mock_client

        note = EHRNote(text="Test note", note_type="Progress note")
        result = await adapter.push_note("pat-1", note)
        assert isinstance(result, PushResult)
        assert result.method == "stub"


# ---------------------------------------------------------------------------
# All adapter methods with mocked FHIR responses
# ---------------------------------------------------------------------------

def _mock_fhir_response(json_body: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestAdapterMethodsWithMockedFHIR:
    """Test each adapter method with mocked FHIR Bundle responses."""

    async def _setup_adapter_with_mock(self, adapter, bundle_response):
        """Inject a mock client that returns the given bundle for GET and a token for POST."""
        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "test-tok", "expires_in": 3600}
        token_resp.raise_for_status = MagicMock()

        fhir_resp = _mock_fhir_response(bundle_response)

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=token_resp)
        mock_client.get = AsyncMock(return_value=fhir_resp)
        adapter._client = mock_client
        return mock_client

    async def test_get_patient(self, adapter, fhir_patient_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_patient_bundle)
        patient = await adapter.get_patient(PatientIdentifier(mrn="MRN-001"))
        assert patient.id == "pat-123"
        assert patient.given_name == "John"
        assert patient.family_name == "Smith"

    async def test_get_problem_list(self, adapter, fhir_condition_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_condition_bundle)
        problems = await adapter.get_problem_list("pat-123")
        assert len(problems) == 1
        assert problems[0].code == "M54.5"
        assert problems[0].description == "Low back pain"
        assert problems[0].status == "active"

    async def test_get_medications(self, adapter, fhir_medication_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_medication_bundle)
        meds = await adapter.get_medications("pat-123")
        assert len(meds) == 1
        assert meds[0].name == "Ibuprofen 400mg"
        assert meds[0].status == "active"
        assert meds[0].route == "Oral"

    async def test_get_allergies(self, adapter, fhir_allergy_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_allergy_bundle)
        allergies = await adapter.get_allergies("pat-123")
        assert len(allergies) == 1
        assert allergies[0].substance == "Penicillin"
        assert allergies[0].reaction == "Hives"
        assert allergies[0].severity == "moderate"

    async def test_get_recent_labs(self, adapter, fhir_observation_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_observation_bundle)
        labs = await adapter.get_recent_labs("pat-123", days=90)
        assert len(labs) == 1
        assert labs[0].name == "Hemoglobin"
        assert labs[0].value == "14.2"
        assert labs[0].unit == "g/dL"
        assert labs[0].reference_range == "12.0-17.5"
        assert labs[0].flag == "N"

    async def test_get_last_visit_note(self, adapter, fhir_document_bundle):
        await self._setup_adapter_with_mock(adapter, fhir_document_bundle)
        note = await adapter.get_last_visit_note("pat-123")
        assert note is not None
        assert note.text == "Patient presents with chronic low back pain."
        assert note.note_type == "Progress note"
        assert note.author == "Dr. Smith"

    async def test_push_note(self, adapter):
        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "test-tok", "expires_in": 3600}
        token_resp.raise_for_status = MagicMock()

        create_resp = MagicMock()
        create_resp.json.return_value = {"id": "doc-new-1", "resourceType": "DocumentReference"}
        create_resp.status_code = 201
        create_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.is_closed = False
        # First POST = token, second POST = create doc
        mock_client.post = AsyncMock(side_effect=[token_resp, create_resp])
        adapter._client = mock_client

        note = EHRNote(text="SOAP note content", note_type="Progress note", author="Dr. Test")
        result = await adapter.push_note("pat-123", note, encounter_id="enc-456")
        assert result.success is True
        assert result.method == "fhir"
        assert result.note_id == "doc-new-1"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    async def test_health_check_returns_true_on_200(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        assert await adapter.health_check() is True

    async def test_health_check_returns_false_on_error(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        adapter._client = mock_client

        assert await adapter.health_check() is False

    async def test_health_check_returns_false_on_non_200(self, adapter):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_client.get = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        assert await adapter.health_check() is False


# ---------------------------------------------------------------------------
# DocumentReference round-trip (serialize → parse)
# ---------------------------------------------------------------------------

class TestDocumentReferenceRoundTrip:
    def test_serialize_and_parse_note(self):
        note = EHRNote(
            text="Assessment: Chronic low back pain",
            note_type="Progress note",
            date="2026-03-01T10:00:00Z",
            author="Dr. Rahman",
        )
        doc_ref = _build_document_reference("pat-123", note, encounter_id="enc-1")
        parsed = _parse_document_reference(doc_ref)
        assert parsed is not None
        assert parsed.text == note.text
        assert parsed.note_type == note.note_type
        assert parsed.author == note.author

    def test_serialize_note_without_author(self):
        note = EHRNote(text="Simple note", note_type="Discharge summary")
        doc_ref = _build_document_reference("pat-1", note)
        assert "author" not in doc_ref
        parsed = _parse_document_reference(doc_ref)
        assert parsed is not None
        assert parsed.text == "Simple note"
        assert parsed.author is None

    def test_serialize_includes_encounter_context(self):
        note = EHRNote(text="Note text", note_type="Progress note")
        doc_ref = _build_document_reference("pat-1", note, encounter_id="enc-99")
        assert doc_ref["context"]["encounter"][0]["reference"] == "Encounter/enc-99"

    def test_serialize_no_encounter(self):
        note = EHRNote(text="Note text", note_type="Progress note")
        doc_ref = _build_document_reference("pat-1", note)
        assert "context" not in doc_ref


# ---------------------------------------------------------------------------
# from_config factory
# ---------------------------------------------------------------------------

class TestFromConfig:
    def test_from_config_basic(self):
        cfg = {
            "fhir_base_url": "https://fhir.epic.com/R4",
            "fhir_vendor": "epic",
            "fhir_client_id": "my-client",
            "fhir_client_secret_env": "TEST_SECRET_ENV",
        }
        with patch.dict("os.environ", {"TEST_SECRET_ENV": "s3cret"}):
            adapter = FHIRAdapter.from_config(cfg)
        assert adapter._base_url == "https://fhir.epic.com/R4"
        assert adapter._vendor == "epic"
        assert adapter.name == "fhir"

    def test_from_config_defaults(self):
        adapter = FHIRAdapter.from_config({})
        assert adapter._base_url == ""
        assert adapter._vendor == "epic"


# ---------------------------------------------------------------------------
# Adapter property: name
# ---------------------------------------------------------------------------

class TestAdapterName:
    def test_name_is_fhir(self, adapter):
        assert adapter.name == "fhir"

    def test_navigate_not_supported(self):
        adapter = FHIRAdapter(fhir_base_url="https://fhir.example.com/R4")

    async def test_navigate_returns_failure(self, adapter):
        result = await adapter.navigate("open chart")
        assert result.success is False
        assert "not supported" in result.error.lower()
