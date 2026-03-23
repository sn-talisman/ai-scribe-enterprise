# FHIR R4 EHR Adapter

## Overview

The FHIR R4 adapter (`mcp_servers/ehr/fhir_server.py`) connects the provider-facing server to live EHR systems (Epic, Cerner, Athena) via the FHIR R4 REST API. It implements the full `EHRAdapter` interface from `mcp_servers/ehr/base.py`, replacing the stub adapter for production use.

All PHI stays on the provider server — nothing is sent to the pipeline.

## Supported EHR Vendors

| Vendor | Token Endpoint | Notes |
|--------|---------------|-------|
| Epic | `/oauth2/token` | Default vendor |
| Cerner | `/token` | |
| Athena | `/oauth2/token` | |

## Configuration

Add an `ehr` section to `config/deployment.yaml`:

```yaml
ehr:
  adapter: "fhir"          # "fhir" or "stub"
  fhir_base_url: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
  fhir_vendor: "epic"      # epic | cerner | athena
  fhir_client_id: "your-client-id"
  fhir_client_secret_env: "AI_SCRIBE_EHR_CLIENT_SECRET"
  fhir_scopes:
    - "patient/*.read"
    - "patient/DocumentReference.write"
```

Set the client secret as an environment variable:
```bash
export AI_SCRIBE_EHR_CLIENT_SECRET="your-secret"
```

## FHIR Resources Used

| Method | FHIR Resource | Operation |
|--------|--------------|-----------|
| `get_patient()` | Patient | Search by MRN or FHIR ID |
| `get_problem_list()` | Condition | Query active conditions |
| `get_medications()` | MedicationRequest | Query active medications |
| `get_allergies()` | AllergyIntolerance | Query allergies |
| `get_recent_labs()` | Observation | Query lab results (default 90 days) |
| `get_last_visit_note()` | DocumentReference | Fetch most recent note |
| `push_note()` | DocumentReference | Create clinical document |

## OAuth2 Authentication

The adapter uses the OAuth2 client_credentials flow. Tokens are cached and automatically refreshed 60 seconds before expiry. On a 401 response, the token is invalidated and one retry is attempted.

## Stub Fallback

If the FHIR endpoint is unreachable (connection error, timeout, HTTP error), the adapter automatically falls back to `StubEHRServer` and logs a warning. This ensures the system remains functional during EHR outages.

## Health Check

`health_check()` hits the FHIR `/metadata` (CapabilityStatement) endpoint. Returns `true` on HTTP 200, `false` otherwise.

## Usage

```python
from mcp_servers.ehr.fhir_server import FHIRAdapter

adapter = FHIRAdapter.from_config({
    "fhir_base_url": "https://fhir.epic.com/.../R4",
    "fhir_vendor": "epic",
    "fhir_client_id": "...",
    "fhir_client_secret_env": "AI_SCRIBE_EHR_CLIENT_SECRET",
})

patient = await adapter.get_patient(PatientIdentifier(mrn="12345"))
```
