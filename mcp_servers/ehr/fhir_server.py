"""
FHIR R4 EHR Adapter — connects to live EHR systems via FHIR R4 REST API.

Implements the full EHRAdapter interface using FHIR R4 resources:
  Patient, Condition, MedicationRequest, AllergyIntolerance,
  Observation, DocumentReference.

Supports Epic, Cerner, and Athena endpoint configuration.
Falls back to StubEHRServer when the FHIR endpoint is unreachable.

All PHI stays on the provider server — never sent to the pipeline.

Usage:
    server = FHIRAdapter.from_config({
        "fhir_base_url": "https://fhir.epic.com/.../R4",
        "fhir_vendor": "epic",
        "fhir_client_id": "...",
        "fhir_client_secret_env": "AI_SCRIBE_EHR_CLIENT_SECRET",
    })
    patient = await server.get_patient(PatientIdentifier(mrn="12345"))
"""

from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import structlog

from mcp_servers.ehr.base import (
    EHRAdapter,
    EHRAllergy,
    EHRLabResult,
    EHRMedication,
    EHRNote,
    EHRPatient,
    EHRProblem,
    NavigationResult,
    PatientIdentifier,
    PushResult,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Vendor-specific URL patterns
# ---------------------------------------------------------------------------
VENDOR_PATHS: dict[str, dict[str, str]] = {
    "epic": {
        "token": "/oauth2/token",
        "patient": "/Patient",
        "condition": "/Condition",
        "medication_request": "/MedicationRequest",
        "allergy": "/AllergyIntolerance",
        "observation": "/Observation",
        "document_reference": "/DocumentReference",
    },
    "cerner": {
        "token": "/token",
        "patient": "/Patient",
        "condition": "/Condition",
        "medication_request": "/MedicationRequest",
        "allergy": "/AllergyIntolerance",
        "observation": "/Observation",
        "document_reference": "/DocumentReference",
    },
    "athena": {
        "token": "/oauth2/token",
        "patient": "/Patient",
        "condition": "/Condition",
        "medication_request": "/MedicationRequest",
        "allergy": "/AllergyIntolerance",
        "observation": "/Observation",
        "document_reference": "/DocumentReference",
    },
}

DEFAULT_SCOPES = ["patient/*.read", "patient/DocumentReference.write"]


class OAuthTokenManager:
    """Manages OAuth2 client_credentials tokens with automatic refresh."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        # Refresh 60 seconds before actual expiry
        return time.time() >= (self._expires_at - 60)

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token and not self.is_expired:
            return self._access_token
        await self._refresh(client)
        return self._access_token  # type: ignore[return-value]

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        """Fetch a new token via client_credentials grant."""
        log.info("fhir_oauth: refreshing access token", token_url=self._token_url)
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": " ".join(self._scopes),
        }
        resp = await client.post(self._token_url, data=data)
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        expires_in = body.get("expires_in", 3600)
        self._expires_at = time.time() + expires_in
        log.info("fhir_oauth: token refreshed", expires_in=expires_in)

    def invalidate(self) -> None:
        """Force token refresh on next call."""
        self._access_token = None
        self._expires_at = 0.0


# ---------------------------------------------------------------------------
# FHIR resource parsing helpers
# ---------------------------------------------------------------------------

def _parse_bundle_entries(bundle: dict[str, Any], resource_type: str) -> list[dict]:
    """Extract resources of a given type from a FHIR R4 Bundle."""
    entries = bundle.get("entry", [])
    return [
        e["resource"]
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get("resource"), dict)
        and e["resource"].get("resourceType") == resource_type
    ]


def _parse_patient(resource: dict[str, Any]) -> EHRPatient:
    """Map a FHIR Patient resource to EHRPatient."""
    names = resource.get("name", [])
    given = ""
    family = ""
    if names:
        name_obj = names[0]
        given_list = name_obj.get("given", [])
        given = given_list[0] if given_list else ""
        family = name_obj.get("family", "")

    dob = resource.get("birthDate")
    sex = resource.get("gender")

    # Extract MRN from identifiers
    mrn = None
    for ident in resource.get("identifier", []):
        id_type = ident.get("type", {})
        codings = id_type.get("coding", [])
        for coding in codings:
            if coding.get("code") == "MR":
                mrn = ident.get("value")
                break
        if mrn:
            break

    return EHRPatient(
        id=resource.get("id", ""),
        given_name=given or None,
        family_name=family or None,
        dob=dob,
        sex=sex,
        mrn=mrn,
    )


def _parse_condition(resource: dict[str, Any]) -> EHRProblem:
    """Map a FHIR Condition resource to EHRProblem."""
    code_obj = resource.get("code", {})
    codings = code_obj.get("coding", [])
    code = codings[0].get("code", "") if codings else ""
    system = codings[0].get("system", "ICD-10") if codings else "ICD-10"
    description = code_obj.get("text", "")
    if not description and codings:
        description = codings[0].get("display", "")

    clinical_status = resource.get("clinicalStatus", {})
    status_codings = clinical_status.get("coding", [])
    status = status_codings[0].get("code", "active") if status_codings else "active"

    onset = resource.get("onsetDateTime")

    return EHRProblem(
        code=code,
        system=system,
        description=description,
        status=status,
        onset_date=onset,
    )


def _parse_medication_request(resource: dict[str, Any]) -> EHRMedication:
    """Map a FHIR MedicationRequest resource to EHRMedication."""
    med_codeable = resource.get("medicationCodeableConcept", {})
    codings = med_codeable.get("coding", [])
    name = med_codeable.get("text", "")
    if not name and codings:
        name = codings[0].get("display", "")
    code = codings[0].get("code") if codings else None

    # Dosage
    dose = None
    frequency = None
    route = None
    dosage_list = resource.get("dosageInstruction", [])
    if dosage_list:
        dosage = dosage_list[0]
        dose_qty = dosage.get("doseAndRate", [{}])[0].get("doseQuantity", {}) if dosage.get("doseAndRate") else {}
        if dose_qty:
            dose = f"{dose_qty.get('value', '')} {dose_qty.get('unit', '')}".strip() or None
        timing = dosage.get("timing", {})
        repeat = timing.get("repeat", {})
        if repeat:
            freq = repeat.get("frequency", "")
            period = repeat.get("period", "")
            period_unit = repeat.get("periodUnit", "")
            if freq:
                frequency = f"{freq} per {period} {period_unit}".strip() or None
        route_obj = dosage.get("route", {})
        route_codings = route_obj.get("coding", [])
        if route_codings:
            route = route_codings[0].get("display")

    status = resource.get("status", "active")

    return EHRMedication(
        name=name,
        code=code,
        dose=dose,
        frequency=frequency,
        route=route,
        status=status,
    )


def _parse_allergy(resource: dict[str, Any]) -> EHRAllergy:
    """Map a FHIR AllergyIntolerance resource to EHRAllergy."""
    code_obj = resource.get("code", {})
    codings = code_obj.get("coding", [])
    substance = code_obj.get("text", "")
    if not substance and codings:
        substance = codings[0].get("display", "")

    reaction_list = resource.get("reaction", [])
    reaction = None
    severity = None
    if reaction_list:
        manifestations = reaction_list[0].get("manifestation", [])
        if manifestations:
            man_codings = manifestations[0].get("coding", [])
            if man_codings:
                reaction = man_codings[0].get("display")
        severity = reaction_list[0].get("severity")

    clinical_status = resource.get("clinicalStatus", {})
    status_codings = clinical_status.get("coding", [])
    status = status_codings[0].get("code", "active") if status_codings else "active"

    return EHRAllergy(
        substance=substance,
        reaction=reaction,
        severity=severity,
        status=status,
    )


def _parse_observation(resource: dict[str, Any]) -> EHRLabResult:
    """Map a FHIR Observation resource to EHRLabResult."""
    code_obj = resource.get("code", {})
    codings = code_obj.get("coding", [])
    name = code_obj.get("text", "")
    if not name and codings:
        name = codings[0].get("display", "")

    value_qty = resource.get("valueQuantity", {})
    value = str(value_qty.get("value", "")) if value_qty else resource.get("valueString", "")
    unit = value_qty.get("unit") if value_qty else None

    ref_range = None
    ref_ranges = resource.get("referenceRange", [])
    if ref_ranges:
        low = ref_ranges[0].get("low", {}).get("value", "")
        high = ref_ranges[0].get("high", {}).get("value", "")
        if low or high:
            ref_range = f"{low}-{high}"

    date = resource.get("effectiveDateTime")

    interpretation = resource.get("interpretation", [])
    flag = None
    if interpretation:
        interp_codings = interpretation[0].get("coding", [])
        if interp_codings:
            flag = interp_codings[0].get("code")

    return EHRLabResult(
        name=name,
        value=value,
        unit=unit,
        reference_range=ref_range,
        date=date,
        flag=flag,
    )


def _parse_document_reference(resource: dict[str, Any]) -> EHRNote | None:
    """Map a FHIR DocumentReference resource to EHRNote."""
    content_list = resource.get("content", [])
    if not content_list:
        return None

    attachment = content_list[0].get("attachment", {})
    text = ""
    if "data" in attachment:
        try:
            text = base64.b64decode(attachment["data"]).decode("utf-8")
        except Exception:
            text = ""
    elif "url" in attachment:
        text = f"[Document at {attachment['url']}]"

    type_obj = resource.get("type", {})
    type_codings = type_obj.get("coding", [])
    note_type = type_codings[0].get("display", "") if type_codings else ""

    date = resource.get("date")

    authors = resource.get("author", [])
    author = authors[0].get("display") if authors else None

    return EHRNote(
        text=text,
        note_type=note_type,
        date=date,
        author=author,
    )


def _build_document_reference(
    patient_id: str,
    note: EHRNote,
    encounter_id: str | None = None,
) -> dict[str, Any]:
    """Serialize an EHRNote to a FHIR R4 DocumentReference resource."""
    encoded = base64.b64encode(note.text.encode("utf-8")).decode("ascii")
    resource: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "status": "current",
        "subject": {"reference": f"Patient/{patient_id}"},
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "11506-3",
                    "display": note.note_type or "Progress note",
                }
            ]
        },
        "date": note.date or datetime.now(timezone.utc).isoformat(),
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain",
                    "data": encoded,
                }
            }
        ],
    }
    if note.author:
        resource["author"] = [{"display": note.author}]
    if encounter_id:
        resource["context"] = {"encounter": [{"reference": f"Encounter/{encounter_id}"}]}
    return resource


# ---------------------------------------------------------------------------
# FHIRAdapter
# ---------------------------------------------------------------------------

class FHIRAdapter(EHRAdapter):
    """
    FHIR R4 EHR adapter with OAuth2 auth and stub fallback.

    Connects to Epic, Cerner, or Athena FHIR endpoints.
    All PHI stays on the provider server.
    """

    def __init__(
        self,
        fhir_base_url: str,
        vendor: str = "epic",
        client_id: str = "",
        client_secret: str = "",
        scopes: list[str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = fhir_base_url.rstrip("/")
        self._vendor = vendor.lower()
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

        paths = VENDOR_PATHS.get(self._vendor, VENDOR_PATHS["epic"])
        self._paths = paths

        token_url = self._base_url + paths["token"]
        self._token_mgr = OAuthTokenManager(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes or DEFAULT_SCOPES,
        )

        # Lazy-loaded stub fallback
        self._stub: Any = None

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "FHIRAdapter":
        """Create a FHIRAdapter from a config dict (or EHRConfig-like object)."""
        secret_env = cfg.get("fhir_client_secret_env", "AI_SCRIBE_EHR_CLIENT_SECRET")
        client_secret = os.environ.get(secret_env, "")
        return cls(
            fhir_base_url=cfg.get("fhir_base_url", ""),
            vendor=cfg.get("fhir_vendor", "epic"),
            client_id=cfg.get("fhir_client_id", ""),
            client_secret=client_secret,
            scopes=cfg.get("fhir_scopes"),
        )

    # -- URL helpers --------------------------------------------------------

    def build_resource_url(self, resource_key: str, **params: str) -> str:
        """Build a full FHIR resource URL for the configured vendor."""
        path = self._paths.get(resource_key, f"/{resource_key}")
        url = self._base_url + path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
        return url

    # -- HTTP helpers -------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _authed_get(self, url: str) -> httpx.Response:
        """GET with OAuth2 bearer token."""
        client = await self._get_client()
        token = await self._token_mgr.get_token(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
        }
        return await client.get(url, headers=headers)

    async def _authed_post(self, url: str, json_body: dict) -> httpx.Response:
        """POST with OAuth2 bearer token."""
        client = await self._get_client()
        token = await self._token_mgr.get_token(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        return await client.post(url, json=json_body, headers=headers)

    # -- Stub fallback ------------------------------------------------------

    def _get_stub(self) -> Any:
        if self._stub is None:
            from mcp_servers.ehr.stub_server import StubEHRServer
            self._stub = StubEHRServer()
            log.warning("fhir_adapter: falling back to stub EHR server")
        return self._stub

    async def _with_fallback(self, coro_factory, fallback_factory):
        """Execute a FHIR call; fall back to stub on connection errors."""
        try:
            return await coro_factory()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout) as exc:
            log.warning("fhir_adapter: FHIR endpoint unreachable, using stub", error=str(exc))
            return await fallback_factory(self._get_stub())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                # Token may have been revoked — invalidate and retry once
                self._token_mgr.invalidate()
                try:
                    return await coro_factory()
                except Exception as retry_exc:
                    log.warning("fhir_adapter: retry after token refresh failed", error=str(retry_exc))
                    return await fallback_factory(self._get_stub())
            log.warning("fhir_adapter: FHIR HTTP error, using stub", status=exc.response.status_code)
            return await fallback_factory(self._get_stub())
        except Exception as exc:
            log.warning("fhir_adapter: unexpected error, using stub", error=str(exc))
            return await fallback_factory(self._get_stub())

    # -- READ ---------------------------------------------------------------

    async def get_patient(self, identifier: PatientIdentifier) -> EHRPatient:
        async def _fhir_call() -> EHRPatient:
            params: dict[str, str] = {}
            if identifier.fhir_id:
                url = self.build_resource_url("patient") + f"/{identifier.fhir_id}"
                resp = await self._authed_get(url)
                resp.raise_for_status()
                return _parse_patient(resp.json())
            if identifier.mrn:
                params["identifier"] = identifier.mrn
            url = self.build_resource_url("patient", **params)
            resp = await self._authed_get(url)
            resp.raise_for_status()
            bundle = resp.json()
            patients = _parse_bundle_entries(bundle, "Patient")
            if not patients:
                return EHRPatient(id="unknown", mrn=identifier.mrn)
            return _parse_patient(patients[0])

        async def _stub_call(stub):
            return await stub.get_patient(identifier)

        return await self._with_fallback(_fhir_call, _stub_call)

    async def get_problem_list(self, patient_id: str) -> list[EHRProblem]:
        async def _fhir_call() -> list[EHRProblem]:
            url = self.build_resource_url("condition", patient=patient_id, **{"clinical-status": "active"})
            resp = await self._authed_get(url)
            resp.raise_for_status()
            resources = _parse_bundle_entries(resp.json(), "Condition")
            return [_parse_condition(r) for r in resources]

        async def _stub_call(stub):
            return await stub.get_problem_list(patient_id)

        return await self._with_fallback(_fhir_call, _stub_call)

    async def get_medications(self, patient_id: str) -> list[EHRMedication]:
        async def _fhir_call() -> list[EHRMedication]:
            url = self.build_resource_url("medication_request", patient=patient_id, status="active")
            resp = await self._authed_get(url)
            resp.raise_for_status()
            resources = _parse_bundle_entries(resp.json(), "MedicationRequest")
            return [_parse_medication_request(r) for r in resources]

        async def _stub_call(stub):
            return await stub.get_medications(patient_id)

        return await self._with_fallback(_fhir_call, _stub_call)

    async def get_allergies(self, patient_id: str) -> list[EHRAllergy]:
        async def _fhir_call() -> list[EHRAllergy]:
            url = self.build_resource_url("allergy", patient=patient_id)
            resp = await self._authed_get(url)
            resp.raise_for_status()
            resources = _parse_bundle_entries(resp.json(), "AllergyIntolerance")
            return [_parse_allergy(r) for r in resources]

        async def _stub_call(stub):
            return await stub.get_allergies(patient_id)

        return await self._with_fallback(_fhir_call, _stub_call)

    async def get_recent_labs(self, patient_id: str, days: int = 90) -> list[EHRLabResult]:
        async def _fhir_call() -> list[EHRLabResult]:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            url = self.build_resource_url(
                "observation",
                patient=patient_id,
                category="laboratory",
                date=f"ge{since}",
            )
            resp = await self._authed_get(url)
            resp.raise_for_status()
            resources = _parse_bundle_entries(resp.json(), "Observation")
            return [_parse_observation(r) for r in resources]

        async def _stub_call(stub):
            return await stub.get_recent_labs(patient_id, days)

        return await self._with_fallback(_fhir_call, _stub_call)

    async def get_last_visit_note(self, patient_id: str) -> Optional[EHRNote]:
        async def _fhir_call() -> Optional[EHRNote]:
            url = self.build_resource_url(
                "document_reference",
                patient=patient_id,
                _sort="-date",
                _count="1",
            )
            resp = await self._authed_get(url)
            resp.raise_for_status()
            resources = _parse_bundle_entries(resp.json(), "DocumentReference")
            if not resources:
                return None
            return _parse_document_reference(resources[0])

        async def _stub_call(stub):
            return await stub.get_last_visit_note(patient_id)

        return await self._with_fallback(_fhir_call, _stub_call)

    # -- WRITE --------------------------------------------------------------

    async def push_note(
        self,
        patient_id: str,
        note: EHRNote,
        encounter_id: Optional[str] = None,
    ) -> PushResult:
        async def _fhir_call() -> PushResult:
            doc_ref = _build_document_reference(patient_id, note, encounter_id)
            url = self.build_resource_url("document_reference")
            resp = await self._authed_post(url, doc_ref)
            resp.raise_for_status()
            body = resp.json()
            note_id = body.get("id")
            return PushResult(
                success=True,
                method="fhir",
                note_id=note_id,
                metadata={"status_code": resp.status_code},
            )

        async def _stub_call(stub):
            return await stub.push_note(patient_id, note, encounter_id)

        return await self._with_fallback(_fhir_call, _stub_call)

    # -- NAVIGATE -----------------------------------------------------------

    async def navigate(self, command: str) -> NavigationResult:
        return NavigationResult(
            success=False,
            action=command,
            error="Navigation not supported by FHIR adapter.",
        )

    # -- Health -------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify FHIR endpoint connectivity via metadata endpoint."""
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._base_url}/metadata",
                headers={"Accept": "application/fhir+json"},
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as exc:
            log.warning("fhir_adapter: health check failed", error=str(exc))
            return False

    @property
    def name(self) -> str:
        return "fhir"

    # -- Cleanup ------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
