"""
api/sync.py — Background config and output sync for provider-facing server.

Periodically pulls templates, providers, specialties, and EHR stub data
from the processing pipeline server to keep the provider-facing server
in sync with the authoritative configuration.

Also provides WebSocket-triggered on-demand output sync: connects to the
Pipeline Server's WebSocket endpoint and listens for ``pipeline.complete``
events.  When received, immediately fetches the generated note and transcript
for that encounter.  Falls back to periodic polling when the WebSocket
connection is unavailable.

Runs as asyncio background tasks during the FastAPI lifespan.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import structlog

from config.deployment import get_deployment_config, ServerRole

logger = structlog.get_logger()

_sync_task: asyncio.Task | None = None


async def start_config_sync() -> None:
    """Start the periodic config sync background task."""
    global _sync_task
    cfg = get_deployment_config()

    # Only run on provider-facing server
    if cfg.role != ServerRole.PROVIDER_FACING:
        logger.info("config_sync_skipped", reason=f"role={cfg.role.value}")
        return

    if not cfg.sync.config_sync.enabled:
        logger.info("config_sync_disabled")
        return

    _sync_task = asyncio.create_task(_sync_loop())
    logger.info("config_sync_started", interval=cfg.sync.config_sync.interval_seconds)


async def stop_config_sync() -> None:
    """Stop the sync background task."""
    global _sync_task
    if _sync_task:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        _sync_task = None
        logger.info("config_sync_stopped")


async def _sync_loop() -> None:
    """Periodically sync config from pipeline server."""
    cfg = get_deployment_config()
    interval = cfg.sync.config_sync.interval_seconds

    while True:
        try:
            await _do_sync()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("config_sync_error", error=str(e))

        await asyncio.sleep(interval)


async def _do_sync() -> None:
    """Execute one sync cycle — pull config items from pipeline server."""
    cfg = get_deployment_config()
    pipeline_url = cfg.pipeline_api_url
    items = cfg.sync.config_sync.items

    headers = {}
    if cfg.inter_server_auth.enabled:
        secret = cfg.inter_server_auth.secret
        if secret:
            headers["X-Inter-Server-Auth"] = secret

    async with httpx.AsyncClient(
        base_url=pipeline_url,
        headers=headers,
        timeout=httpx.Timeout(60.0),
    ) as client:
        synced = []

        if "providers" in items:
            try:
                resp = await client.get("/providers")
                resp.raise_for_status()
                providers = resp.json()
                _sync_providers(providers)
                synced.append(f"providers({len(providers)})")
            except Exception as e:
                logger.warning("sync_providers_failed", error=str(e))

        if "templates" in items:
            try:
                resp = await client.get("/templates")
                resp.raise_for_status()
                templates = resp.json()
                _sync_templates(templates, client)
                synced.append(f"templates({len(templates)})")
            except Exception as e:
                logger.warning("sync_templates_failed", error=str(e))

        if "dictionaries" in items:
            try:
                resp = await client.get("/specialties")
                resp.raise_for_status()
                specialties = resp.json()
                await _sync_specialties(specialties, client)
                synced.append(f"specialties({len(specialties)})")
            except Exception as e:
                logger.warning("sync_specialties_failed", error=str(e))

        logger.info("config_sync_complete", synced=synced)


def _sync_providers(providers: list[dict]) -> None:
    """Write provider profiles to local config/providers/."""
    from config.paths import PROVIDERS_DIR
    PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)

    for p in providers:
        provider_id = p.get("id", "")
        if not provider_id:
            continue
        # Only sync the summary — full profile needs a detail fetch
        # For now, write a minimal YAML if it doesn't exist locally
        local_path = PROVIDERS_DIR / f"{provider_id}.yaml"
        if not local_path.exists():
            import yaml
            profile = {
                "id": provider_id,
                "name": p.get("name", ""),
                "credentials": p.get("credentials", ""),
                "specialty": p.get("specialty", ""),
            }
            local_path.write_text(yaml.dump(profile, default_flow_style=False))
            logger.info("sync_provider_created", provider_id=provider_id)


def _sync_templates(templates: list[dict], client: httpx.AsyncClient) -> None:
    """Write template summaries to local config/templates/."""
    from config.paths import CONFIG_DIR
    template_dir = CONFIG_DIR / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    for t in templates:
        template_id = t.get("id", "")
        if not template_id:
            continue
        local_path = template_dir / f"{template_id}.yaml"
        # Don't overwrite existing templates — admin manages these
        # Only create missing ones (new templates created on pipeline server)
        if not local_path.exists():
            logger.info("sync_template_new", template_id=template_id,
                       msg="New template detected — fetch detail on next sync")


async def _sync_specialties(specialties: list[dict], client: httpx.AsyncClient) -> None:
    """Sync specialty dictionaries from pipeline server."""
    from config.paths import CONFIG_DIR
    dict_dir = CONFIG_DIR / "dictionaries"
    dict_dir.mkdir(parents=True, exist_ok=True)

    for s in specialties:
        specialty_id = s.get("id", "")
        if not specialty_id:
            continue
        local_path = dict_dir / f"{specialty_id}.txt"
        if not local_path.exists():
            # Fetch the full specialty detail
            try:
                resp = await client.get(f"/specialties/{specialty_id}")
                resp.raise_for_status()
                detail = resp.json()
                terms = detail.get("terms", [])
                local_path.write_text("\n".join(terms) + "\n")
                logger.info("sync_specialty_created", specialty_id=specialty_id,
                           term_count=len(terms))
            except Exception as e:
                logger.warning("sync_specialty_fetch_failed",
                             specialty_id=specialty_id, error=str(e))


async def sync_outputs_from_pipeline(sample_ids: list[str], since: str = "") -> dict:
    """
    Pull generated outputs from the pipeline server for specific samples.

    Called by the data sync scripts or on-demand when checking for new results.
    Returns a summary of what was synced.
    """
    cfg = get_deployment_config()
    if cfg.role not in (ServerRole.PROVIDER_FACING,):
        return {"synced": 0, "message": "Output sync only runs on provider-facing server"}

    from api.proxy import proxy_batch_outputs, proxy_get_note, proxy_get_transcript
    from config.paths import OUTPUT_DIR

    manifest = await proxy_batch_outputs(sample_ids, since)
    samples = manifest.get("samples", [])
    synced_files = 0

    for sample in samples:
        sid = sample["sample_id"]
        for file_info in sample.get("files", []):
            fname = file_info["filename"]
            # Determine where to write locally
            # We need to know the mode and physician for the path
            # For now, fetch via the output endpoints
            if fname.startswith("generated_note_"):
                version = fname.replace("generated_note_", "").replace(".md", "")
                try:
                    data = await proxy_get_note(sid, version)
                    # Write to local output dir (need to find the right path)
                    _write_synced_output(sid, fname, data.get("content", ""))
                    synced_files += 1
                except Exception:
                    pass
            elif fname.startswith("audio_transcript_"):
                version = fname.replace("audio_transcript_", "").replace(".txt", "")
                try:
                    data = await proxy_get_transcript(sid, version)
                    _write_synced_output(sid, fname, data.get("content", ""))
                    synced_files += 1
                except Exception:
                    pass

    return {"synced": synced_files, "samples": len(samples)}


def _write_synced_output(sample_id: str, filename: str, content: str) -> None:
    """Write a synced output file to the local output directory."""
    from config.paths import OUTPUT_DIR

    # Find the sample's output directory
    for mode_dir in ["dictation", "conversation"]:
        mode_path = OUTPUT_DIR / mode_dir
        if not mode_path.exists():
            continue
        for physician_dir in mode_path.iterdir():
            if not physician_dir.is_dir():
                continue
            sample_dir = physician_dir / sample_id
            if sample_dir.exists():
                dest = sample_dir / filename
                dest.write_text(content)
                return

    # If not found, can't determine path without more context
    logger.warning("sync_output_no_local_dir", sample_id=sample_id, filename=filename)


# ---------------------------------------------------------------------------
# Incremental sync and conflict resolution (Requirements 12.3, 12.4)
# ---------------------------------------------------------------------------

from email.utils import parsedate_to_datetime, format_datetime
from datetime import datetime, timezone


class IncrementalSync:
    """Fetch only files where the remote timestamp is strictly newer than local.

    Uses ``Last-Modified`` / ``If-Modified-Since`` HTTP headers to avoid
    re-downloading unchanged files.
    """

    @staticmethod
    def should_fetch(local_path: Path, remote_last_modified: str) -> bool:
        """Return True if the remote file is strictly newer than the local copy.

        Parameters
        ----------
        local_path:
            Path to the local file.  If it does not exist, always returns True.
        remote_last_modified:
            HTTP ``Last-Modified`` header value (RFC 2822 / RFC 7231 format).
        """
        if not local_path.exists():
            return True

        try:
            remote_dt = parsedate_to_datetime(remote_last_modified)
        except Exception:
            # If we can't parse the remote timestamp, fetch to be safe
            return True

        local_mtime = datetime.fromtimestamp(
            local_path.stat().st_mtime, tz=timezone.utc
        )

        return remote_dt > local_mtime

    @staticmethod
    async def fetch_if_newer(
        client: httpx.AsyncClient,
        url: str,
        local_path: Path,
    ) -> bool:
        """Send an ``If-Modified-Since`` request; write file only on HTTP 200.

        Returns True if the file was downloaded (200), False if not modified
        (304) or on error.
        """
        headers: dict[str, str] = {}
        if local_path.exists():
            local_mtime = datetime.fromtimestamp(
                local_path.stat().st_mtime, tz=timezone.utc
            )
            headers["If-Modified-Since"] = format_datetime(local_mtime, usegmt=True)

        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 304:
                logger.debug("incremental_sync_not_modified", url=url)
                return False
            resp.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(resp.text)
            logger.info("incremental_sync_fetched", url=url, path=str(local_path))
            return True
        except Exception as exc:
            logger.warning("incremental_sync_error", url=url, error=str(exc))
            return False


class ConflictResolver:
    """Resolve conflicts when both local and remote versions are modified.

    Strategy options:
    - ``keep_both`` (default): rename local with ``.local`` suffix, write remote
      at original path.
    - ``keep_remote``: overwrite local with remote content.
    - ``keep_local``: skip remote, keep local unchanged.
    """

    def __init__(self, strategy: str = "keep_both") -> None:
        self.strategy = strategy

    def resolve(
        self,
        local_path: Path,
        remote_content: str,
        remote_timestamp: str,
    ) -> Path:
        """Handle a conflict for *local_path*.

        Returns the path where the remote content was written (or the
        original local path if the local version was kept).
        """
        if self.strategy == "keep_local":
            logger.info(
                "conflict_keep_local",
                path=str(local_path),
            )
            return local_path

        if self.strategy == "keep_remote":
            local_path.write_text(remote_content, encoding="utf-8")
            logger.info(
                "conflict_keep_remote",
                path=str(local_path),
            )
            return local_path

        # Default: keep_both — rename local, write remote at original path
        backup_path = local_path.with_suffix(local_path.suffix + ".local")
        if local_path.exists():
            backup_path.write_text(local_path.read_text(encoding="utf-8"), encoding="utf-8")
        local_path.write_text(remote_content, encoding="utf-8")
        logger.info(
            "conflict_keep_both",
            path=str(local_path),
            backup=str(backup_path),
            remote_timestamp=remote_timestamp,
        )
        return local_path


# ---------------------------------------------------------------------------
# WebSocket-triggered on-demand output sync (Requirements 12.1, 12.2, 12.5)
# ---------------------------------------------------------------------------

# Try to import websockets; if unavailable, WebSocket mode is disabled and
# the class falls back to periodic polling immediately.
try:
    import websockets  # type: ignore[import-untyped]
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False


def _derive_ws_url(pipeline_api_url: str) -> str:
    """Derive a WebSocket URL from the pipeline HTTP API URL.

    Replaces ``http`` with ``ws`` (and ``https`` with ``wss``) and appends
    the ``/ws/events`` path.
    """
    url = pipeline_api_url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    return url + "/ws/events"


class OutputSyncWebSocket:
    """Connect to the Pipeline Server WebSocket and sync outputs on demand.

    On receiving a ``pipeline.complete`` event the class immediately fetches
    the generated note and transcript for the encounter.  If the WebSocket
    connection drops it falls back to the existing periodic polling
    (``_sync_loop``) and attempts reconnection after *reconnect_interval*
    seconds.
    """

    def __init__(
        self,
        pipeline_ws_url: str,
        auth_secret: str | None = None,
        reconnect_interval: float = 30.0,
    ) -> None:
        self.pipeline_ws_url = pipeline_ws_url
        self.auth_secret = auth_secret
        self.reconnect_interval = reconnect_interval

        self._ws_task: asyncio.Task | None = None
        self._fallback_task: asyncio.Task | None = None
        self._running = False
        self._ws_connected = False

    # -- public API ---------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket listener (or fall back to polling)."""
        if self._running:
            return
        self._running = True

        if not _HAS_WEBSOCKETS:
            logger.warning(
                "output_sync_ws_unavailable",
                reason="websockets library not installed, falling back to polling",
            )
            self._start_fallback_polling()
            return

        self._ws_task = asyncio.create_task(self._reconnect_loop())
        logger.info(
            "output_sync_ws_started",
            ws_url=self.pipeline_ws_url,
            reconnect_interval=self.reconnect_interval,
        )

    async def stop(self) -> None:
        """Cleanly shut down the WebSocket connection and any fallback tasks."""
        self._running = False

        for task in (self._ws_task, self._fallback_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._ws_task = None
        self._fallback_task = None
        self._ws_connected = False
        logger.info("output_sync_ws_stopped")

    # -- internal -----------------------------------------------------------

    async def _reconnect_loop(self) -> None:
        """Repeatedly attempt to connect; on failure wait and retry."""
        while self._running:
            try:
                await self._listen_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._ws_connected = False
                logger.warning(
                    "output_sync_ws_disconnected",
                    error=str(exc),
                    retry_in=self.reconnect_interval,
                )
                # Fall back to periodic polling while disconnected
                self._start_fallback_polling()

            if not self._running:
                break
            await asyncio.sleep(self.reconnect_interval)

    async def _listen_loop(self) -> None:
        """Connect to the WebSocket and process messages until disconnect."""
        extra_headers = {}
        if self.auth_secret:
            extra_headers["X-Inter-Server-Auth"] = self.auth_secret

        async with websockets.connect(  # type: ignore[attr-defined]
            self.pipeline_ws_url,
            additional_headers=extra_headers,
        ) as ws:
            self._ws_connected = True
            self._stop_fallback_polling()
            logger.info("output_sync_ws_connected", ws_url=self.pipeline_ws_url)

            async for raw_message in ws:
                if not self._running:
                    break
                try:
                    message = json.loads(raw_message)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("output_sync_ws_bad_message", raw=str(raw_message)[:200])
                    continue

                event_type = message.get("event") or message.get("type")
                if event_type == "pipeline.complete":
                    encounter_id = message.get("encounter_id") or message.get("id")
                    if encounter_id:
                        asyncio.create_task(
                            self._handle_pipeline_complete(encounter_id)
                        )

    async def _handle_pipeline_complete(self, encounter_id: str) -> None:
        """Fetch note and transcript for *encounter_id* from the pipeline."""
        cfg = get_deployment_config()
        pipeline_url = cfg.pipeline_api_url

        headers: dict[str, str] = {}
        if cfg.inter_server_auth.enabled and cfg.inter_server_auth.secret:
            headers["X-Inter-Server-Auth"] = cfg.inter_server_auth.secret

        async with httpx.AsyncClient(
            base_url=pipeline_url,
            headers=headers,
            timeout=httpx.Timeout(60.0),
        ) as client:
            # Fetch note
            try:
                resp = await client.get(f"/pipeline/output/{encounter_id}/note")
                resp.raise_for_status()
                note_data = resp.json()
                content = note_data.get("content", "")
                filename = note_data.get("filename", f"generated_note_{encounter_id}.md")
                _write_synced_output(encounter_id, filename, content)
                logger.info("output_sync_note_fetched", encounter_id=encounter_id)
            except Exception as exc:
                logger.warning(
                    "output_sync_note_failed",
                    encounter_id=encounter_id,
                    error=str(exc),
                )

            # Fetch transcript
            try:
                resp = await client.get(f"/pipeline/output/{encounter_id}/transcript")
                resp.raise_for_status()
                transcript_data = resp.json()
                content = transcript_data.get("content", "")
                filename = transcript_data.get(
                    "filename", f"audio_transcript_{encounter_id}.txt"
                )
                _write_synced_output(encounter_id, filename, content)
                logger.info("output_sync_transcript_fetched", encounter_id=encounter_id)
            except Exception as exc:
                logger.warning(
                    "output_sync_transcript_failed",
                    encounter_id=encounter_id,
                    error=str(exc),
                )

    def _start_fallback_polling(self) -> None:
        """Start periodic polling as a fallback when WebSocket is down."""
        if self._fallback_task is None or self._fallback_task.done():
            self._fallback_task = asyncio.create_task(self._fallback_poll_loop())
            logger.info("output_sync_fallback_polling_started")

    def _stop_fallback_polling(self) -> None:
        """Stop the fallback polling task (WebSocket reconnected)."""
        if self._fallback_task is not None and not self._fallback_task.done():
            self._fallback_task.cancel()
            self._fallback_task = None
            logger.info("output_sync_fallback_polling_stopped")

    async def _fallback_poll_loop(self) -> None:
        """Periodic polling loop — mirrors ``_sync_loop`` for output sync."""
        cfg = get_deployment_config()
        interval = cfg.sync.config_sync.interval_seconds

        while self._running and not self._ws_connected:
            try:
                await _do_sync()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("output_sync_fallback_error", error=str(exc))
            await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Module-level output sync lifecycle
# ---------------------------------------------------------------------------

_output_sync_ws: OutputSyncWebSocket | None = None


async def start_output_sync() -> None:
    """Start the WebSocket-based output sync (provider-facing only)."""
    global _output_sync_ws
    cfg = get_deployment_config()

    if cfg.role != ServerRole.PROVIDER_FACING:
        logger.info("output_sync_skipped", reason=f"role={cfg.role.value}")
        return

    if not cfg.sync.output_sync.enabled:
        logger.info("output_sync_disabled")
        return

    pipeline_ws_url = _derive_ws_url(cfg.pipeline_api_url)
    auth_secret = (
        cfg.inter_server_auth.secret if cfg.inter_server_auth.enabled else None
    )

    _output_sync_ws = OutputSyncWebSocket(
        pipeline_ws_url=pipeline_ws_url,
        auth_secret=auth_secret,
    )
    await _output_sync_ws.start()


async def stop_output_sync() -> None:
    """Stop the WebSocket-based output sync."""
    global _output_sync_ws
    if _output_sync_ws is not None:
        await _output_sync_ws.stop()
        _output_sync_ws = None
