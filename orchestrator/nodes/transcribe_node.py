"""
TRANSCRIBE NODE — ASR, diarization, and post-processing.

Flow:
  PRE:  pass-through guard (if transcript already set, skip ASR)
        build ASR config (custom vocab, speaker count)
  CORE: transcribe_batch_sync (via WhisperXServer or injected engine)
  POST: convert RawTranscript → UnifiedTranscript
        run 12-stage post-processor (medasr_postprocessor.py)
        score ASR confidence
        update state

Engine selection: WhisperXServer by default (config/engines.yaml).
Override for testing: call set_asr_engine_factory(fn) before running the graph.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from mcp_servers.asr.base import ASRConfig, ASREngine, RawTranscript
from orchestrator.state import (
    EncounterState,
    EncounterStatus,
    RecordingMode,
    TranscriptSegment,
    UnifiedTranscript,
    WordToken,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Engine factory (injectable for testing — mirrors note_node pattern)
# ─────────────────────────────────────────────────────────────────────────────

_asr_engine_factory: Optional[Callable[[], ASREngine]] = None


def set_asr_engine_factory(factory: Optional[Callable[[], ASREngine]]) -> None:
    """
    Override the ASR engine factory used by transcribe_node.

    Pass None to restore the default (registry lookup from engines.yaml).

    Example:
        set_asr_engine_factory(lambda: MockASREngine())
    """
    global _asr_engine_factory
    _asr_engine_factory = factory


def _default_engine_factory() -> ASREngine:
    from mcp_servers.registry import get_registry
    return get_registry().get_asr()


def _get_asr_engine() -> ASREngine:
    factory = _asr_engine_factory or _default_engine_factory
    return factory()


# ─────────────────────────────────────────────────────────────────────────────
# RawTranscript → UnifiedTranscript conversion
# ─────────────────────────────────────────────────────────────────────────────

def _raw_to_unified(
    raw: RawTranscript,
    mode: RecordingMode,
) -> UnifiedTranscript:
    """Convert WhisperX RawTranscript into the pipeline's UnifiedTranscript."""
    segments: list[TranscriptSegment] = []
    for seg in raw.segments:
        words = [
            WordToken(
                text=w.text,
                start_ms=w.start_ms,
                end_ms=w.end_ms,
                confidence=w.confidence,
            )
            for w in seg.words
        ]
        segments.append(
            TranscriptSegment(
                text=seg.text,
                speaker=seg.speaker,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                confidence=seg.confidence,
                words=words,
                mode=mode,
                source="asr",
            )
        )

    full_text = " ".join(s.text for s in raw.segments)

    return UnifiedTranscript(
        segments=segments,
        engine_used=raw.engine,
        diarization_engine="pyannote-3.1" if raw.diarization_applied else "",
        audio_duration_ms=raw.audio_duration_ms,
        full_text=full_text,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing integration
# ─────────────────────────────────────────────────────────────────────────────

def _apply_postprocessor(
    transcript: UnifiedTranscript,
    mode: str = "hybrid",
) -> tuple[UnifiedTranscript, dict, str]:
    """
    Run the 12-stage post-processor over transcript.full_text.

    Segment texts keep their original form (timing/speaker info is sacred).
    full_text is updated with the cleaned version for LLM consumption.
    """
    from postprocessor import run_postprocessor

    if not transcript.full_text.strip():
        return transcript, {}, "none"

    try:
        cleaned_text, pp_metrics = run_postprocessor(
            transcript.full_text,
            use_medical_spellcheck=(mode in ("hybrid", "rules_only")),
        )
        updated = transcript.model_copy(update={"full_text": cleaned_text})
        logger.debug(
            "postprocessor: stutter_pairs=%d char_stutters=%d medical=%d",
            pp_metrics.get("stutter_pairs_merged", 0),
            pp_metrics.get("char_stutters_fixed", 0),
            pp_metrics.get("medical_corrections", 0),
        )
        return updated, pp_metrics, "medasr_postprocessor_v1"
    except Exception as exc:
        logger.warning("postprocessor: failed (%s), skipping", exc)
        return transcript, {}, "error"


# ─────────────────────────────────────────────────────────────────────────────
# Confidence scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_asr_confidence(transcript: UnifiedTranscript) -> float:
    """Average word-level confidence across all segments."""
    all_confs = [
        w.confidence
        for seg in transcript.segments
        for w in seg.words
        if w.confidence is not None
    ]
    if not all_confs:
        seg_confs = [s.confidence for s in transcript.segments]
        return round(sum(seg_confs) / len(seg_confs), 3) if seg_confs else 0.0
    return round(sum(all_confs) / len(all_confs), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Node entry point
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_node(state: EncounterState) -> dict:
    """
    Transcribe audio to a cleaned, diarized UnifiedTranscript.

    Pass-through: if state.transcript is already populated (e.g., injected for
    testing or from manual text input), skip ASR and pass through unchanged.

    Falls back gracefully if the ASR engine is unavailable.
    """
    logger.info("transcribe_node: start", extra={"encounter_id": state.encounter_id})
    t0 = time.monotonic_ns()
    errors = list(state.errors)

    # ── Pass-through guard ────────────────────────────────────────────────
    if state.transcript and state.transcript.full_text:
        logger.info(
            "transcribe_node: transcript already present, pass-through",
            extra={"encounter_id": state.encounter_id},
        )
        elapsed_ms = (time.monotonic_ns() - t0) // 1_000_000
        return {
            "status": EncounterStatus.PROCESSING,
            "transcript": state.transcript,
            "asr_engine_used": state.asr_engine_used or "passthrough",
            "diarization_engine_used": state.diarization_engine_used or "passthrough",
            "postprocessor_version": "none",
            "metrics": state.metrics.model_copy(
                update={
                    "asr_duration_ms": elapsed_ms,
                    "nodes_completed": state.metrics.nodes_completed + ["transcribe"],
                }
            ),
        }

    # ── Resolve audio path ────────────────────────────────────────────────
    audio_path: Optional[str] = state.audio_file_path
    if not audio_path and state.audio_segments:
        audio_path = state.audio_segments[0].storage_path

    if not audio_path:
        logger.error("transcribe_node: no audio source available",
                     extra={"encounter_id": state.encounter_id})
        errors.append("transcribe_node: no audio_file_path or audio_segments")
        return _fallback_result(state, errors, t0, "no_audio")

    # ── Build ASR config ──────────────────────────────────────────────────
    mode = state.recording_mode
    diarize = (mode == RecordingMode.AMBIENT)
    asr_cfg = ASRConfig(
        language="en",
        diarize=diarize,
        max_speakers=5 if diarize else 1,
        custom_vocabulary=state.provider_profile.custom_vocabulary,
    )

    # ── Transcribe ────────────────────────────────────────────────────────
    try:
        engine = _get_asr_engine()
        logger.info("transcribe_node: calling %s on %s", engine.name, audio_path,
                    extra={"encounter_id": state.encounter_id})

        raw: RawTranscript = engine.transcribe_batch_sync(audio_path, asr_cfg)
        transcript = _raw_to_unified(raw, mode)
        asr_engine_used = f"{raw.engine}/{raw.model}"
        diarization_used = raw.engine if raw.diarization_applied else ""

    except Exception as exc:
        logger.error("transcribe_node: ASR failed — %s", exc,
                     extra={"encounter_id": state.encounter_id})
        errors.append(f"transcribe_node: {type(exc).__name__}: {exc}")
        return _fallback_result(state, errors, t0, "asr_error")

    # ── Post-process ──────────────────────────────────────────────────────
    pp_mode = state.provider_profile.postprocessor_mode
    transcript, pp_metrics, pp_version = _apply_postprocessor(transcript, mode=pp_mode)
    asr_confidence = _score_asr_confidence(transcript)

    elapsed_ms = (time.monotonic_ns() - t0) // 1_000_000
    logger.info(
        "transcribe_node: done — %d segs, %.1fs audio, conf=%.2f, pp=%s",
        len(transcript.segments),
        transcript.audio_duration_ms / 1000,
        asr_confidence,
        pp_version,
        extra={"encounter_id": state.encounter_id},
    )

    return {
        "status": EncounterStatus.PROCESSING,
        "transcript": transcript,
        "asr_engine_used": asr_engine_used,
        "diarization_engine_used": diarization_used,
        "postprocessor_version": pp_version,
        "postprocessor_metrics": pp_metrics,
        "errors": errors,
        "metrics": state.metrics.model_copy(
            update={
                "asr_duration_ms": elapsed_ms,
                "asr_confidence": asr_confidence,
                "postprocessor_corrections": (
                    pp_metrics.get("stutter_pairs_merged", 0)
                    + pp_metrics.get("char_stutters_fixed", 0)
                    + pp_metrics.get("medical_corrections", 0)
                ),
                "stutter_pairs_removed": pp_metrics.get("stutter_pairs_merged", 0),
                "nodes_completed": state.metrics.nodes_completed + ["transcribe"],
            }
        ),
    }


def _fallback_result(
    state: EncounterState,
    errors: list[str],
    t0: int,
    reason: str,
) -> dict:
    """Return a stub transcript when ASR fails so downstream nodes still run."""
    elapsed_ms = (time.monotonic_ns() - t0) // 1_000_000
    stub_text = f"[ASR UNAVAILABLE: {reason}]"
    transcript = UnifiedTranscript(
        segments=[
            TranscriptSegment(
                text=stub_text,
                speaker="SPEAKER_00",
                start_ms=0,
                end_ms=0,
                mode=state.recording_mode,
                source="asr",
            )
        ],
        engine_used="fallback_stub",
        full_text=stub_text,
    )
    return {
        "status": EncounterStatus.PROCESSING,
        "transcript": transcript,
        "asr_engine_used": "fallback_stub",
        "diarization_engine_used": "",
        "postprocessor_version": "none",
        "errors": errors,
        "metrics": state.metrics.model_copy(
            update={
                "asr_duration_ms": elapsed_ms,
                "nodes_completed": state.metrics.nodes_completed + ["transcribe"],
            }
        ),
    }
