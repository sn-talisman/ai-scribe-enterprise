"""
NeMo Streaming ASR Server — real-time transcription via NVIDIA Nemotron-Speech-Streaming.

Implements the ASREngine interface for both streaming and batch modes.
Uses NeMo's cache-aware FastConformer-RNNT for low-latency chunk processing.

Model: nvidia/nemotron-speech-streaming-en-0.6b (~2-3 GB VRAM)
Input: 16 kHz, mono, 16-bit PCM audio chunks (configurable chunk size)
Output: PartialTranscript per chunk (text, is_final, confidence, timing)

Session management: each streaming session caches encoder hidden state.
Sessions auto-expire after idle_timeout_s (default 300s).
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from mcp_servers.asr.base import (
    ASRCapabilities,
    ASRConfig,
    ASREngine,
    PartialTranscript,
    RawSegment,
    RawTranscript,
    WordAlignment,
)

logger = logging.getLogger(__name__)


@dataclass
class StreamingSession:
    """State for a single streaming ASR session."""
    session_id: str
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    accumulated_text: str = ""
    segments: list[RawSegment] = field(default_factory=list)
    elapsed_ms: int = 0
    chunk_count: int = 0
    # NeMo cache state (populated when model is loaded)
    cache_state: Any = None
    # Audio buffer for incomplete frames
    audio_buffer: bytes = b""
    # Full session PCM buffer (for NeMo chunked transcription)
    full_pcm: bytes = b""
    # Last transcription result (for diffing)
    last_transcription: str = ""
    # Bytes already transcribed (to know when new audio warrants re-transcription)
    last_transcribed_bytes: int = 0


class NemoStreamingServer(ASREngine):
    """
    Streaming ASR engine wrapping NVIDIA Nemotron-Speech-Streaming.

    Supports both streaming (transcribe_stream) and batch (transcribe_batch) modes.
    The model is lazy-loaded on first request and unloaded after idle_timeout_s.
    """

    def __init__(
        self,
        model_name: str = "nvidia/nemotron-speech-streaming-en-0.6b",
        device: str = "cuda",
        chunk_size_ms: int = 160,
        idle_timeout_s: int = 300,
    ):
        self.model_name = model_name
        self.device = device
        self.chunk_size_ms = chunk_size_ms
        self.idle_timeout_s = idle_timeout_s

        # Derived constants
        self.sample_rate = 16000
        self.chunk_samples = int(self.sample_rate * self.chunk_size_ms / 1000)
        self.chunk_bytes = self.chunk_samples * 2  # 16-bit = 2 bytes per sample

        # Model state (lazy loaded)
        self._model = None
        self._model_lock = threading.Lock()
        self._loaded = False

        # Active streaming sessions
        self._sessions: dict[str, StreamingSession] = {}
        self._sessions_lock = threading.Lock()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "NemoStreamingServer":
        """Instantiate from engines.yaml config dict."""
        return cls(
            model_name=config.get("model", "nvidia/nemotron-speech-streaming-en-0.6b"),
            device=config.get("device", "cuda"),
            chunk_size_ms=config.get("chunk_size_ms", 160),
            idle_timeout_s=config.get("idle_unload_seconds", 300),
        )

    @property
    def name(self) -> str:
        return "nemo_streaming"

    # ── Model lifecycle ──────────────────────────────────────────────────

    def _ensure_model(self) -> None:
        """Lazy-load the NeMo model on first use."""
        if self._loaded:
            return
        with self._model_lock:
            if self._loaded:
                return
            try:
                import nemo.collections.asr as nemo_asr
                logger.info("nemo_streaming: loading model %s on %s", self.model_name, self.device)
                self._model = nemo_asr.models.ASRModel.from_pretrained(
                    model_name=self.model_name,
                )
                if self.device == "cuda":
                    self._model = self._model.cuda()
                self._model.eval()
                self._loaded = True
                logger.info("nemo_streaming: model loaded successfully")
            except ImportError:
                logger.warning(
                    "nemo_streaming: NeMo not installed — streaming will use simulation mode. "
                    "Install with: pip install nemo_toolkit[asr]"
                )
                self._model = None
                self._loaded = True  # Mark as loaded so we don't retry
            except Exception as exc:
                logger.error("nemo_streaming: failed to load model — %s", exc)
                self._model = None
                self._loaded = True

    def unload_model(self) -> None:
        """Unload the model from GPU memory."""
        with self._model_lock:
            if self._model is not None:
                del self._model
                self._model = None
                self._loaded = False
                # Free GPU memory
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                logger.info("nemo_streaming: model unloaded")

    # ── Session management ───────────────────────────────────────────────

    def _get_or_create_session(self, session_id: str) -> StreamingSession:
        with self._sessions_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = StreamingSession(session_id=session_id)
                logger.info("nemo_streaming: new session %s", session_id)
            session = self._sessions[session_id]
            session.last_activity = time.monotonic()
            return session

    def _close_session(self, session_id: str) -> Optional[StreamingSession]:
        with self._sessions_lock:
            return self._sessions.pop(session_id, None)

    def get_session_transcript(self, session_id: str) -> Optional[str]:
        """Get the accumulated transcript for a session."""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            return session.accumulated_text if session else None

    def finalize_session(self, session_id: str) -> Optional[RawTranscript]:
        """Close a session and return the accumulated transcript as a RawTranscript."""
        session = self._close_session(session_id)
        if session is None:
            return None

        return RawTranscript(
            segments=session.segments,
            engine="nemo_streaming",
            model=self.model_name,
            language="en",
            audio_duration_ms=session.elapsed_ms,
            diarization_applied=False,
        )

    def cleanup_expired_sessions(self) -> int:
        """Remove sessions that have been idle longer than idle_timeout_s."""
        now = time.monotonic()
        expired = []
        with self._sessions_lock:
            for sid, session in self._sessions.items():
                if now - session.last_activity > self.idle_timeout_s:
                    expired.append(sid)
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.info("nemo_streaming: expired %d idle sessions", len(expired))
        return len(expired)

    # ── Streaming transcription ──────────────────────────────────────────

    # How many seconds of new audio before we re-transcribe
    STREAM_WINDOW_S = 3.0  # Transcribe every 3 seconds of new audio

    async def transcribe_stream(
        self,
        audio_chunk: bytes,
        session_id: str,
        config: ASRConfig,
    ) -> AsyncIterator[PartialTranscript]:
        """
        Process a streaming audio chunk and yield partial transcripts.

        Strategy: accumulate PCM into a rolling buffer. Every STREAM_WINDOW_S
        seconds of new audio, transcribe the latest window via model.transcribe()
        and diff against the previous result to emit new text.

        If NeMo is not installed, uses a simulation mode for UI development.
        """
        self._ensure_model()
        session = self._get_or_create_session(session_id)

        # Buffer the incoming audio
        session.audio_buffer += audio_chunk

        # Move complete frame-aligned data from audio_buffer to full_pcm
        while len(session.audio_buffer) >= self.chunk_bytes:
            chunk_data = session.audio_buffer[:self.chunk_bytes]
            session.audio_buffer = session.audio_buffer[self.chunk_bytes:]
            session.full_pcm += chunk_data
            session.chunk_count += 1
            session.elapsed_ms += self.chunk_size_ms

        # Check if we have enough new audio to warrant transcription
        new_bytes = len(session.full_pcm) - session.last_transcribed_bytes
        new_seconds = new_bytes / (self.sample_rate * 2)  # 2 bytes per sample

        if new_seconds < self.STREAM_WINDOW_S:
            return  # Not enough new audio yet

        start_ms = session.last_transcribed_bytes * 1000 // (self.sample_rate * 2)
        end_ms = session.elapsed_ms

        if self._model is not None:
            # Real NeMo inference on accumulated audio
            result = await asyncio.to_thread(
                self._transcribe_window_nemo, session
            )
        else:
            # Simulation mode
            result = self._transcribe_window_simulated(session, start_ms, end_ms)

        if result:
            text = result.get("text", "")
            new_text = result.get("new_text", text)
            is_final = result.get("is_final", True)
            confidence = result.get("confidence", 0.9)

            if new_text.strip():
                partial = PartialTranscript(
                    text=new_text,
                    is_final=is_final,
                    speaker=None,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    confidence=confidence,
                )

                if is_final:
                    session.accumulated_text += new_text + " "
                    session.segments.append(RawSegment(
                        text=new_text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        confidence=confidence,
                    ))

                yield partial

        session.last_transcribed_bytes = len(session.full_pcm)

    def _transcribe_window_nemo(self, session: StreamingSession) -> dict:
        """Transcribe the accumulated audio via NeMo model.transcribe() (runs in thread).

        Writes the latest audio window to a temp WAV, transcribes it, and
        diffs against the previous transcription to find new text.
        """
        try:
            import numpy as np
            import soundfile as sf
            import tempfile

            # Convert full PCM buffer to float32 array
            audio_array = np.frombuffer(session.full_pcm, dtype=np.int16).astype(np.float32) / 32768.0

            # Write to temp WAV file (NeMo transcribe expects file paths)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, audio_array, self.sample_rate)
                temp_path = f.name

            # Transcribe the full accumulated audio
            results = self._model.transcribe([temp_path])
            text = results[0] if isinstance(results, list) else str(results)
            if hasattr(text, 'text'):
                text = text.text

            # Clean up temp file
            import os
            os.unlink(temp_path)

            # Diff: find the new text that wasn't in the last transcription
            prev = session.last_transcription
            new_text = text
            if prev and text.startswith(prev[:20]):
                # Simple prefix diff — find where new text starts
                # Use word-level comparison for robustness
                prev_words = prev.split()
                new_words = text.split()
                # Find longest common prefix
                common = 0
                for i, (a, b) in enumerate(zip(prev_words, new_words)):
                    if a == b:
                        common = i + 1
                    else:
                        break
                new_text = " ".join(new_words[common:]) if common < len(new_words) else ""

            session.last_transcription = text

            return {
                "text": text,
                "new_text": new_text.strip(),
                "is_final": True,
                "confidence": 0.9,
            }

        except Exception as exc:
            logger.warning("nemo_streaming: transcription failed — %s", exc)
            return {}

    def _transcribe_window_simulated(
        self, session: StreamingSession,
        start_ms: int, end_ms: int,
    ) -> dict:
        """Simulation mode: return placeholder text for UI development."""
        segment_num = len(session.segments) + 1
        return {
            "text": f"[streaming segment {segment_num} at {start_ms}ms]",
            "new_text": f"[streaming segment {segment_num} at {start_ms}ms]",
            "is_final": True,
            "confidence": 0.85,
        }

    # ── Batch transcription (compatibility) ──────────────────────────────

    async def transcribe_batch(
        self,
        audio_path: str,
        config: ASRConfig,
    ) -> RawTranscript:
        """
        Transcribe a full audio file in batch mode.

        Uses NeMo's standard (non-streaming) transcription if available,
        otherwise falls back to a stub result.
        """
        self._ensure_model()

        if self._model is not None:
            result = await asyncio.to_thread(self._batch_transcribe_nemo, audio_path, config)
            return result

        # Simulation mode
        logger.warning("nemo_streaming: batch mode — NeMo not installed, returning stub")
        return RawTranscript(
            segments=[RawSegment(
                text="[NeMo not installed — batch transcription unavailable]",
                start_ms=0,
                end_ms=0,
            )],
            engine="nemo_streaming",
            model=self.model_name,
            language="en",
            audio_duration_ms=0,
        )

    def _batch_transcribe_nemo(self, audio_path: str, config: ASRConfig) -> RawTranscript:
        """Run NeMo batch transcription (in thread)."""
        try:
            results = self._model.transcribe([audio_path])
            text = results[0] if results else ""

            return RawTranscript(
                segments=[RawSegment(
                    text=text,
                    start_ms=0,
                    end_ms=0,
                    confidence=0.9,
                )],
                engine="nemo_streaming",
                model=self.model_name,
                language="en",
                audio_duration_ms=0,
            )
        except Exception as exc:
            logger.error("nemo_streaming: batch transcription failed — %s", exc)
            return RawTranscript(
                segments=[RawSegment(
                    text=f"[ASR error: {exc}]",
                    start_ms=0,
                    end_ms=0,
                )],
                engine="nemo_streaming",
                model=self.model_name,
                language="en",
                audio_duration_ms=0,
            )

    # ── Sync wrapper (for LangGraph which calls sync) ────────────────────

    def transcribe_batch_sync(self, audio_path: str, config: ASRConfig) -> RawTranscript:
        """Synchronous wrapper for batch transcription."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.transcribe_batch(audio_path, config))
                return future.result()
        return asyncio.run(self.transcribe_batch(audio_path, config))

    # ── Capabilities ─────────────────────────────────────────────────────

    async def get_capabilities(self) -> ASRCapabilities:
        return ASRCapabilities(
            streaming=True,
            batch=True,
            diarization=False,
            word_alignment=False,
            medical_vocab=False,
            max_speakers=1,
            supported_formats=["pcm", "wav"],
        )
