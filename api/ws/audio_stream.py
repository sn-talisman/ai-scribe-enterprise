"""
api/ws/audio_stream.py — WebSocket endpoint for real-time audio streaming + ASR.

Protocol:
  Client → Server: binary audio chunks (WebM/Opus from MediaRecorder, or raw PCM)
  Server → Client: JSON messages
    { "type": "partial",  "text": "...", "is_final": false, "confidence": 0.9 }
    { "type": "final",    "text": "...", "is_final": true, "speaker": "SPEAKER_00", "start_ms": 1200, "end_ms": 3400 }
    { "type": "complete", "transcript": "Full accumulated transcript..." }
    { "type": "error",    "message": "..." }

Audio conversion: if the client sends WebM/Opus (browser MediaRecorder default),
the server pipes it through FFmpeg to convert to 16kHz mono PCM in real-time.

This endpoint runs on the pipeline server only (requires GPU for NeMo).
The provider-facing server proxies WebSocket connections to the pipeline server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from config.deployment import get_deployment_config, require_feature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Active streaming ASR sessions
_active_sessions: dict[str, dict] = {}


def _get_streaming_engine(mode: str = "dictation"):
    """Get the appropriate streaming ASR engine for the recording mode."""
    from mcp_servers.registry import get_registry
    registry = get_registry()

    if mode == "ambient":
        # Try multitalker first for multi-speaker
        try:
            engine = registry.get("asr", "nemo_multitalker")
            return engine
        except (KeyError, ImportError):
            pass

    # Default: single-speaker NeMo streaming
    try:
        engine = registry.get("asr", "nemo_streaming")
        return engine
    except (KeyError, ImportError):
        logger.warning("audio_stream: no streaming ASR engine available")
        return None


class AudioConverter:
    """
    Converts streaming WebM/Opus audio to 16kHz mono PCM via FFmpeg pipe.

    Receives WebM chunks on stdin, outputs raw PCM on stdout.
    Runs as a subprocess for zero-copy streaming conversion.
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None

    async def start(self) -> None:
        """Start the FFmpeg conversion subprocess."""
        self._process = await asyncio.to_thread(self._start_ffmpeg)

    def _start_ffmpeg(self) -> subprocess.Popen:
        return subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",           # Read from stdin
                "-f", "s16le",            # Output raw PCM
                "-acodec", "pcm_s16le",   # 16-bit signed
                "-ar", "16000",           # 16 kHz
                "-ac", "1",               # Mono
                "pipe:1",                 # Write to stdout
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    async def write(self, chunk: bytes) -> None:
        """Write a WebM chunk to FFmpeg's stdin."""
        if self._process and self._process.stdin:
            try:
                await asyncio.to_thread(self._process.stdin.write, chunk)
                await asyncio.to_thread(self._process.stdin.flush)
            except (BrokenPipeError, OSError):
                logger.warning("audio_stream: FFmpeg pipe broken")

    async def read(self, num_bytes: int) -> bytes:
        """Read converted PCM bytes from FFmpeg's stdout."""
        if self._process and self._process.stdout:
            try:
                return await asyncio.to_thread(self._process.stdout.read, num_bytes)
            except (BrokenPipeError, OSError):
                return b""
        return b""

    async def close(self) -> None:
        """Terminate the FFmpeg process."""
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                await asyncio.to_thread(self._process.wait, timeout=5)
            except Exception:
                self._process.kill()
            self._process = None


@router.websocket("/ws/asr/{encounter_id}")
async def asr_stream(
    encounter_id: str,
    websocket: WebSocket,
    mode: str = Query("dictation"),
    format: str = Query("webm"),
):
    """
    WebSocket for real-time audio streaming + ASR transcription.

    Query params:
        mode: "dictation" (single speaker) or "ambient" (multi-speaker)
        format: "webm" (browser default) or "pcm" (raw 16kHz mono 16-bit)

    Client sends binary audio frames. Server responds with JSON transcript events.
    """
    await websocket.accept()

    engine = _get_streaming_engine(mode)
    if engine is None:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "No streaming ASR engine available. Install NeMo or check engines.yaml.",
        }))
        await websocket.close()
        return

    # Set up audio format conversion if needed
    converter: Optional[AudioConverter] = None
    needs_conversion = (format != "pcm")

    if needs_conversion:
        converter = AudioConverter()
        try:
            await converter.start()
        except Exception as exc:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Failed to start audio converter: {exc}",
            }))
            await websocket.close()
            return

    # Track session
    session_id = encounter_id
    from mcp_servers.asr.base import ASRConfig
    asr_config = ASRConfig(
        language="en",
        diarize=(mode == "ambient"),
    )

    _active_sessions[session_id] = {
        "encounter_id": encounter_id,
        "mode": mode,
        "started_at": time.time(),
        "chunks_received": 0,
    }

    await websocket.send_text(json.dumps({
        "type": "connected",
        "encounter_id": encounter_id,
        "mode": mode,
        "engine": engine.name,
    }))

    logger.info("asr_stream: session started — encounter=%s mode=%s engine=%s",
                encounter_id, mode, engine.name)

    accumulated_transcript = ""

    try:
        while True:
            # Receive audio chunk from client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_bytes(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            _active_sessions[session_id]["chunks_received"] = (
                _active_sessions[session_id].get("chunks_received", 0) + 1
            )

            # Convert audio format if needed
            if needs_conversion and converter:
                await converter.write(data)
                # Read available PCM data (non-blocking, read what's available)
                pcm_data = await converter.read(
                    engine.chunk_bytes * 2  # Read up to 2 chunks worth
                )
                if not pcm_data:
                    continue
            else:
                pcm_data = data

            # Feed to streaming ASR engine
            async for partial in engine.transcribe_stream(pcm_data, session_id, asr_config):
                event = {
                    "type": "final" if partial.is_final else "partial",
                    "text": partial.text,
                    "is_final": partial.is_final,
                    "speaker": partial.speaker,
                    "start_ms": partial.start_ms,
                    "end_ms": partial.end_ms,
                    "confidence": partial.confidence,
                }
                await websocket.send_text(json.dumps(event))

                if partial.is_final:
                    accumulated_transcript += partial.text + " "

    except WebSocketDisconnect:
        logger.info("asr_stream: client disconnected — encounter=%s", encounter_id)
    except Exception as exc:
        logger.error("asr_stream: error — %s", exc)
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": str(exc),
            }))
        except Exception:
            pass
    finally:
        # Finalize session
        raw_transcript = engine.finalize_session(session_id)

        # Send complete transcript to client
        try:
            final_text = accumulated_transcript.strip()
            if raw_transcript and raw_transcript.segments:
                final_text = " ".join(s.text for s in raw_transcript.segments)

            await websocket.send_text(json.dumps({
                "type": "complete",
                "transcript": final_text,
                "segments": [
                    {
                        "text": s.text,
                        "speaker": s.speaker,
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "confidence": s.confidence,
                    }
                    for s in (raw_transcript.segments if raw_transcript else [])
                ],
            }))
        except Exception:
            pass

        # Cleanup
        if converter:
            await converter.close()
        _active_sessions.pop(session_id, None)

        logger.info("asr_stream: session ended — encounter=%s chunks=%d transcript_len=%d",
                     encounter_id,
                     _active_sessions.get(session_id, {}).get("chunks_received", 0),
                     len(accumulated_transcript))
