"""
tests/unit/test_output_sync_websocket.py — Tests for OutputSyncWebSocket.

Covers initialization, WebSocket URL derivation, pipeline-complete handling,
fallback to polling on WebSocket failure, reconnect logic, and clean shutdown.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.sync import OutputSyncWebSocket, _derive_ws_url


# ---------------------------------------------------------------------------
# URL derivation
# ---------------------------------------------------------------------------

class TestDeriveWsUrl:
    """WebSocket URL derivation from pipeline API URL."""

    def test_http_to_ws(self):
        assert _derive_ws_url("http://pipeline:8100") == "ws://pipeline:8100/ws/events"

    def test_https_to_wss(self):
        assert _derive_ws_url("https://pipeline.example.com") == "wss://pipeline.example.com/ws/events"

    def test_trailing_slash_stripped(self):
        assert _derive_ws_url("http://pipeline:8100/") == "ws://pipeline:8100/ws/events"

    def test_preserves_path_prefix(self):
        """If the API URL already has a path, it's kept."""
        assert _derive_ws_url("http://host:8100/api/v1") == "ws://host:8100/api/v1/ws/events"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestOutputSyncWebSocketInit:
    """OutputSyncWebSocket initialization."""

    def test_default_reconnect_interval(self):
        ws = OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")
        assert ws.reconnect_interval == 30.0
        assert ws.auth_secret is None
        assert ws._running is False
        assert ws._ws_connected is False

    def test_custom_reconnect_interval(self):
        ws = OutputSyncWebSocket(
            pipeline_ws_url="ws://localhost:8100/ws/events",
            auth_secret="my-secret",
            reconnect_interval=10.0,
        )
        assert ws.reconnect_interval == 10.0
        assert ws.auth_secret == "my-secret"

    def test_zero_reconnect_interval(self):
        ws = OutputSyncWebSocket(
            pipeline_ws_url="ws://localhost:8100/ws/events",
            reconnect_interval=0,
        )
        assert ws.reconnect_interval == 0


# ---------------------------------------------------------------------------
# _handle_pipeline_complete
# ---------------------------------------------------------------------------

class TestHandlePipelineComplete:
    """Fetching note + transcript on pipeline.complete."""

    @pytest.fixture()
    def ws_instance(self):
        return OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")

    async def test_fetches_note_and_transcript(self, ws_instance):
        """Both GET /pipeline/output/{id}/note and .../transcript are called."""
        note_resp = MagicMock()
        note_resp.json.return_value = {"content": "SOAP note", "filename": "generated_note_v9.md"}
        note_resp.raise_for_status = MagicMock()

        transcript_resp = MagicMock()
        transcript_resp.json.return_value = {"content": "transcript text", "filename": "audio_transcript_v9.txt"}
        transcript_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[note_resp, transcript_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("api.sync.httpx.AsyncClient", return_value=mock_client), \
             patch("api.sync._write_synced_output") as mock_write, \
             patch("api.sync.get_deployment_config") as mock_cfg:

            cfg = MagicMock()
            cfg.pipeline_api_url = "http://localhost:8100"
            cfg.inter_server_auth.enabled = False
            mock_cfg.return_value = cfg

            await ws_instance._handle_pipeline_complete("enc_001")

            # Two GET calls: note + transcript
            assert mock_client.get.call_count == 2
            calls = [c.args[0] for c in mock_client.get.call_args_list]
            assert "/pipeline/output/enc_001/note" in calls
            assert "/pipeline/output/enc_001/transcript" in calls

            # Two writes
            assert mock_write.call_count == 2

    async def test_note_failure_still_fetches_transcript(self, ws_instance):
        """If note fetch fails, transcript fetch should still be attempted."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            Exception("note endpoint down"),
            MagicMock(
                json=MagicMock(return_value={"content": "transcript", "filename": "t.txt"}),
                raise_for_status=MagicMock(),
            ),
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("api.sync.httpx.AsyncClient", return_value=mock_client), \
             patch("api.sync._write_synced_output") as mock_write, \
             patch("api.sync.get_deployment_config") as mock_cfg:

            cfg = MagicMock()
            cfg.pipeline_api_url = "http://localhost:8100"
            cfg.inter_server_auth.enabled = False
            mock_cfg.return_value = cfg

            await ws_instance._handle_pipeline_complete("enc_002")

            # Note failed, transcript succeeded → 1 write
            assert mock_write.call_count == 1

    async def test_auth_header_included_when_enabled(self, ws_instance):
        """Inter-server auth header should be passed to httpx client."""
        mock_client = AsyncMock()
        # Both calls raise so we don't need full response mocks
        mock_client.get = AsyncMock(side_effect=Exception("not important"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("api.sync.httpx.AsyncClient", return_value=mock_client) as mock_cls, \
             patch("api.sync._write_synced_output"), \
             patch("api.sync.get_deployment_config") as mock_cfg:

            cfg = MagicMock()
            cfg.pipeline_api_url = "http://localhost:8100"
            cfg.inter_server_auth.enabled = True
            cfg.inter_server_auth.secret = "s3cret"
            mock_cfg.return_value = cfg

            await ws_instance._handle_pipeline_complete("enc_003")

            # Verify the auth header was passed
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["headers"]["X-Inter-Server-Auth"] == "s3cret"


# ---------------------------------------------------------------------------
# Fallback to polling on WebSocket failure
# ---------------------------------------------------------------------------

class TestFallbackPolling:
    """When WebSocket is unavailable, fall back to periodic polling."""

    async def test_fallback_when_websockets_missing(self):
        """If websockets library is not installed, start() enables fallback polling."""
        ws = OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")

        with patch("api.sync._HAS_WEBSOCKETS", False):
            await ws.start()

            assert ws._running is True
            # Fallback task should have been created
            assert ws._fallback_task is not None
            assert ws._ws_task is None

            await ws.stop()

    async def test_fallback_started_on_ws_disconnect(self):
        """When _reconnect_loop catches an exception, fallback polling starts."""
        ws = OutputSyncWebSocket(
            pipeline_ws_url="ws://localhost:8100/ws/events",
            reconnect_interval=0.05,
        )
        ws._running = True

        call_count = 0

        async def fake_listen_loop():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("ws down")
            # On third call, stop the loop
            ws._running = False

        with patch.object(ws, "_listen_loop", side_effect=fake_listen_loop), \
             patch.object(ws, "_start_fallback_polling") as mock_fallback:
            await ws._reconnect_loop()

            # Fallback should have been started on each failure
            assert mock_fallback.call_count >= 1


# ---------------------------------------------------------------------------
# Reconnect logic
# ---------------------------------------------------------------------------

class TestReconnectLogic:
    """Reconnect loop retries after configurable interval."""

    async def test_reconnect_respects_interval(self):
        """The reconnect loop should sleep for reconnect_interval between retries."""
        ws = OutputSyncWebSocket(
            pipeline_ws_url="ws://localhost:8100/ws/events",
            reconnect_interval=0.01,
        )
        ws._running = True

        attempts = 0

        async def fake_listen():
            nonlocal attempts
            attempts += 1
            if attempts >= 3:
                ws._running = False
                return
            raise ConnectionError("down")

        with patch.object(ws, "_listen_loop", side_effect=fake_listen), \
             patch.object(ws, "_start_fallback_polling"):
            await ws._reconnect_loop()

        assert attempts == 3


# ---------------------------------------------------------------------------
# stop() clean shutdown
# ---------------------------------------------------------------------------

class TestStopShutdown:
    """stop() cleanly cancels all tasks."""

    async def test_stop_cancels_ws_task(self):
        ws = OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")
        ws._running = True

        # Create a dummy long-running task
        async def forever():
            await asyncio.sleep(3600)

        ws._ws_task = asyncio.create_task(forever())
        await ws.stop()

        assert ws._running is False
        assert ws._ws_task is None
        assert ws._ws_connected is False

    async def test_stop_cancels_fallback_task(self):
        ws = OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")
        ws._running = True

        async def forever():
            await asyncio.sleep(3600)

        ws._fallback_task = asyncio.create_task(forever())
        await ws.stop()

        assert ws._fallback_task is None

    async def test_stop_idempotent(self):
        """Calling stop() when already stopped should not raise."""
        ws = OutputSyncWebSocket(pipeline_ws_url="ws://localhost:8100/ws/events")
        await ws.stop()
        await ws.stop()  # no error
