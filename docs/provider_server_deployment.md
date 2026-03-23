# Provider Server Deployment Guide (Windows)

This guide covers deploying the AI Scribe provider-facing server on Windows, including automated setup, service management, and the Phase 2 ecosystem enhancements.

## Quick Start

```powershell
# From the project root, run the deployment script:
.\deploy\setup_provider_server.ps1 `
  -PipelineUrl "http://pipeline-server:8100" `
  -PublicUrl "https://provider.example.com" `
  -WithNginx -WithService
```

This single command handles configuration generation, directory creation, NTFS ACLs, nginx reverse proxy, NSSM service registration, and health checks.

## Deployment Script Parameters

| Parameter | Required | Description |
|---|---|---|
| `-PipelineUrl` | Yes | Internal URL of the processing-pipeline server |
| `-PublicUrl` | No | Public-facing URL for the provider API |
| `-Secret` | No | Inter-server auth secret (auto-generated if omitted, min 32 chars, URL-safe) |
| `-WithNginx` | No | Install and configure nginx as HTTPS reverse proxy |
| `-TlsCert` | No | Path to TLS certificate (self-signed generated if omitted) |
| `-TlsKey` | No | Path to TLS private key |
| `-WithService` | No | Register API + Web UI as Windows services via NSSM |

## What the Script Does

### 1. Configuration Generation
- Creates `.env.provider` with `AI_SCRIBE_SERVER_ROLE=provider-facing`, data paths, pipeline URL, and inter-server secret
- Updates `config/deployment.yaml` with pipeline URL, public URL, and enables inter-server auth
- Generates a cryptographically secure secret if `-Secret` is not provided

### 2. Data Directories + NTFS ACLs
Creates seven directories with locked-down permissions (FullControl for service account + SYSTEM only, inherited permissions removed):
- `ai-scribe-data\dictation`, `ai-scribe-data\conversation`
- `output\dictation`, `output\conversation`
- `config\providers`, `config\templates`, `config\dictionaries`

### 3. nginx Reverse Proxy (`-WithNginx`)
- HTTPS on port 443, HTTP→HTTPS redirect on port 80
- Reverse proxy: `/api/` → `:8000`, `/` → `:3000`
- WebSocket upgrade headers for `/ws/` paths
- Rate limiting at 100 req/s per client IP
- Self-signed TLS cert generated if no cert/key paths provided

### 4. NSSM Services (`-WithService`)
- `ai-scribe-api`: Uvicorn on port 8000, auto-start, 5s restart delay
- `ai-scribe-web`: Next.js on port 3000, depends on `ai-scribe-api`, auto-start, 5s restart delay
- Both load environment from `.env.provider`

### 5. Health Checks
- Verifies local API at `http://localhost:8000/health` (failure = exit non-zero)
- Verifies pipeline server at configured URL (failure = warning, continues)

## Docker Deployment

```powershell
docker-compose -f deploy/docker-compose.provider.yml up -d
```

Environment variables in the compose file:
- `AI_SCRIBE_SERVER_ROLE=provider-facing`
- `AI_SCRIBE_INTER_SERVER_SECRET` (set via `.env` or shell)
- `PIPELINE_API_URL` (defaults to `http://pipeline:8100`)

## Phase 2 Enhancements

### EHR FHIR R4 Integration
- `mcp_servers/ehr/fhir_server.py` — full FHIR R4 adapter supporting Epic, Cerner, and Athena
- OAuth2 token management with automatic refresh
- Falls back to EHR stub when FHIR endpoint is unreachable
- Configured via `ehr` section in `deployment.yaml` (see `docs/fhir_ehr_adapter.md`)

### Output Sync Enhancements
- WebSocket-triggered on-demand sync from pipeline server
- Incremental sync with `If-Modified-Since` headers
- Conflict resolution: `keep_both` (default), `keep_remote`, `keep_local`
- See `docs/output_sync_enhancements.md`

### Provider Web UI Enhancements
- Note editor with split-pane markdown preview, save/approve workflow
- Correction diff engine for tracking provider edits by SOAP section
- Practice branding (name, logo, color) from `deployment.yaml`
- See `docs/provider_web_ui_enhancements.md`

## Test Suite

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/ -v
```

Team A tests (170+) cover deployment config generation, directory creation, NTFS ACLs, nginx config, NSSM services, health checks, FHIR adapter, output sync, incremental sync, and branding config.
