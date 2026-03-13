#!/usr/bin/env python3
"""
Batch evaluation: run pipeline on all dictation + conversation samples.

Audio resolution per sample folder:
  conversation.mp3  → RecordingMode.AMBIENT
  dictation.mp3     → RecordingMode.DICTATION   (fallback if no conversation.mp3)

Gold note resolution:
  soap_final.md     → used for data/dictation/ samples
  soap_initial.md   → used for data/conversations/ samples

Saves per-sample artifacts alongside each sample:
    <sample_dir>/generated_note_v{N}.md   — formatted clinical note
    <sample_dir>/comparison_v{N}.md       — side-by-side Markdown table vs gold

Saves aggregate report:
    output/batch_report_v{N}.md

Usage:
    python scripts/batch_eval.py [--version v1]
    python scripts/batch_eval.py --version v2 --data-dir data/conversations
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_DATA_DIRS = ["data/dictation", "data/conversations"]


def _discover_ollama_model() -> str:
    import httpx
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        models = resp.json().get("models", [])
        if models:
            return models[0]["name"]
    except Exception:
        pass
    return "qwen2.5:32b"


def _resolve_sample(sample_dir: Path) -> tuple[Path | None, str, Path | None]:
    """
    Resolve audio file, recording mode, and gold note path for a sample dir.

    Returns:
        (audio_path, mode_str, gold_path) — audio_path/gold_path may be None
    """
    # Audio: prefer conversation.mp3 (AMBIENT), fall back to dictation.mp3
    conversation = sample_dir / "conversation.mp3"
    dictation = sample_dir / "dictation.mp3"

    if conversation.exists():
        audio_path = conversation
        mode = "ambient"
    elif dictation.exists():
        audio_path = dictation
        mode = "dictation"
    else:
        return None, "dictation", None

    # Gold note: soap_final.md (dictation samples) or soap_initial.md (conversation samples)
    for gold_name in ("soap_final.md", "soap_initial.md"):
        gold = sample_dir / gold_name
        if gold.exists():
            return audio_path, mode, gold

    return audio_path, mode, None


def _collect_samples(data_dirs: list[str]) -> list[tuple[Path, str, Path | None]]:
    """Return list of (audio_path, mode_str, gold_path) for all runnable samples."""
    samples = []
    for data_dir_str in data_dirs:
        data_dir = Path(data_dir_str)
        if not data_dir.exists():
            continue
        for sample_dir in sorted(data_dir.iterdir()):
            if not sample_dir.is_dir():
                continue
            audio_path, mode, gold_path = _resolve_sample(sample_dir)
            if audio_path:
                samples.append((audio_path, mode, gold_path))
    return samples


def run_sample(audio_path: Path, mode: str, gold_path: Path | None, graph, version: str, out_dir: Path) -> dict:
    from orchestrator.graph import run_encounter
    from orchestrator.state import (
        DeliveryMethod, EncounterState,
        RecordingMode,
    )
    from output.markdown_writer import write_clinical_note
    from output.comparison_writer import write_comparison

    sample_id = audio_path.parent.name
    gold_note = gold_path.read_text() if gold_path else ""
    recording_mode = RecordingMode.AMBIENT if mode == "ambient" else RecordingMode.DICTATION
    # Mirror data/ folder structure: output/dictation/<id>/ or output/conversations/<id>/
    # Route by source data folder (not audio mode) so samples from data/conversations/
    # always appear in output/conversations/ regardless of their recording mode.
    subfolder = "conversations" if "conversations" in str(audio_path) else "dictation"
    sample_out_dir = out_dir / subfolder / sample_id
    sample_out_dir.mkdir(parents=True, exist_ok=True)

    from config.provider_manager import get_provider_manager
    mgr = get_provider_manager()
    # Load real provider profile; fall back to orthopedic default if not found
    provider_profile = mgr.load_or_default("dr_faraz_rahman")

    state = EncounterState(
        provider_id=provider_profile.id,
        patient_id=f"patient-{sample_id}",
        provider_profile=provider_profile,
        recording_mode=recording_mode,
        delivery_method=DeliveryMethod.CLIPBOARD,
        audio_file_path=str(audio_path),
    )

    t0 = time.time()
    final = run_encounter(graph, state)
    elapsed = time.time() - t0

    generated_note = final.final_note.to_text() if final.final_note else ""

    write_clinical_note(
        final,
        path=sample_out_dir / f"generated_note_{version}.md",
        version=version,
        sample_id=sample_id,
    )

    # Save standalone transcript (plain text, one file per pipeline version)
    if final.transcript and final.transcript.full_text.strip():
        transcript_path = sample_out_dir / f"audio_transcript_{version}.txt"
        transcript_path.write_text(final.transcript.full_text.strip())

    metrics = {
        "asr_engine": final.asr_engine_used,
        "asr_conf": f"{final.metrics.asr_confidence:.2f}" if final.metrics.asr_confidence else "—",
        "note_conf": f"{final.metrics.note_confidence:.2f}" if final.metrics.note_confidence else "—",
        "pp_corrections": final.metrics.postprocessor_corrections or 0,
        "asr_ms": final.metrics.asr_duration_ms or 0,
        "llm_ms": final.metrics.note_gen_ms or 0,
    }
    overlap = write_comparison(
        path=sample_out_dir / f"comparison_{version}.md",
        sample_id=sample_id,
        generated_note=generated_note,
        gold_note=gold_note,
        transcript=final.transcript.full_text if final.transcript else "",
        metrics=metrics,
        version=version,
    )

    return {
        "id": sample_id,
        "mode": mode,
        "audio": audio_path.name,
        "elapsed": elapsed,
        "asr_ms": final.metrics.asr_duration_ms or 0,
        "llm_ms": final.metrics.note_gen_ms or 0,
        "asr_engine": final.asr_engine_used,
        "llm_engine": final.llm_engine_used,
        "asr_conf": final.metrics.asr_confidence or 0.0,
        "note_conf": final.metrics.note_confidence or 0.0,
        "pp_corrections": final.metrics.postprocessor_corrections or 0,
        "overlap": overlap,
        "has_gold": bool(gold_note),
        "errors": final.errors,
        "segments": len(final.transcript.segments) if final.transcript else 0,
        "audio_duration_s": (final.transcript.audio_duration_ms or 0) / 1000 if final.transcript else 0,
    }


def write_batch_report(results: list[dict], model: str, version: str, total_elapsed: float, out_dir: Path) -> None:
    overlaps = [r["overlap"] for r in results if r.get("has_gold") and not r.get("errors")]
    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
    avg_elapsed = total_elapsed / len(results) if results else 0

    dictation_results = [r for r in results if r["mode"] == "dictation"]
    ambient_results = [r for r in results if r["mode"] == "ambient"]

    lines = [
        f"# Batch Report — Pipeline {version}",
        "",
        f"**Model:** {model}  ",
        f"**Samples:** {len(results)} ({len(dictation_results)} dictation, {len(ambient_results)} ambient)  ",
        f"**Total time:** {total_elapsed:.0f}s  ",
        f"**Avg per sample:** {avg_elapsed:.1f}s  ",
        f"**Avg keyword overlap:** {avg_overlap:.0%}  ",
        "",
        "---",
        "",
        "## Per-Sample Results",
        "",
        "| Sample | Mode | Audio | Duration | ASR ms | LLM ms | ASR conf | Note conf | PP | Overlap | Status |",
        "|--------|------|-------|----------|--------|--------|----------|-----------|----|---------|--------|",
    ]

    for r in results:
        status = "⚠ " + "; ".join(r["errors"]) if r.get("errors") else "✓"
        overlap_str = f"{r['overlap']:.0%}" if r.get("has_gold") else "—"
        lines.append(
            f"| {r['id']} "
            f"| {r['mode']} "
            f"| {r['audio']} "
            f"| {r['elapsed']:.1f}s "
            f"| {r['asr_ms']} "
            f"| {r['llm_ms']} "
            f"| {r['asr_conf']:.2f} "
            f"| {r['note_conf']:.2f} "
            f"| {r['pp_corrections']} "
            f"| {overlap_str} "
            f"| {status} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Averages",
        "",
        "| Metric | All | Dictation | Ambient |",
        "|--------|-----|-----------|---------|",
    ]

    def _avg(lst, key):
        vals = [r[key] for r in lst if not r.get("errors")]
        return f"{sum(vals)/len(vals):.2f}" if vals else "—"

    def _avg_overlap(lst):
        vals = [r["overlap"] for r in lst if r.get("has_gold") and not r.get("errors")]
        return f"{sum(vals)/len(vals):.0%}" if vals else "—"

    for label, key in [("Elapsed", "elapsed"), ("ASR conf", "asr_conf"), ("Note conf", "note_conf"), ("PP corrections", "pp_corrections")]:
        lines.append(f"| {label} | {_avg(results, key)} | {_avg(dictation_results, key)} | {_avg(ambient_results, key)} |")
    lines.append(f"| Keyword overlap | {_avg_overlap(results)} | {_avg_overlap(dictation_results)} | {_avg_overlap(ambient_results)} |")
    lines.append(f"| Errors | {sum(1 for r in results if r.get('errors'))}/{len(results)} | {sum(1 for r in dictation_results if r.get('errors'))}/{len(dictation_results)} | {sum(1 for r in ambient_results if r.get('errors'))}/{len(ambient_results)} |")

    lines += [
        "",
        "---",
        "",
        "## Notes",
        "",
        "- Keyword overlap measures domain-relevant word matches between generated and gold notes",
        "- Low overlap expected for v1 (no templates, no patient context)",
        "- v2 (Session 5) adds specialty templates; v3 (Session 7) adds patient demographics",
        "- Ambient mode uses diarization (pyannote); dictation mode is single-speaker",
        "",
        f"*Generated by AI Scribe batch_eval.py — version {version}*",
        "",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"batch_report_{version}.md"
    report_path.write_text("\n".join(lines))
    print(f"Batch report : {report_path}")


def _two_pass_main(args, samples: list, model: str) -> tuple[list, float]:
    """
    Two-pass execution for large LLMs (e.g. qwen2.5:32b) that cannot share VRAM
    with WhisperX large-v3 on a single GPU.

    Pass 1 — ASR only:  run all samples through the transcription pipeline, save
                         transcript state (text + segments) to JSON per sample.
    Pass 2 — LLM only:  unload WhisperX, load each saved transcript into a stub
                         ASR engine, run the note-generation pipeline.
    """
    import json
    import torch
    import json
    import torch
    from orchestrator.graph import build_graph
    from orchestrator.nodes.note_node import set_llm_engine_factory
    from orchestrator.nodes.transcribe_node import set_asr_engine_factory
    from mcp_servers.llm.base import LLMEngine, LLMConfig, LLMMessage, LLMResponse, ModelInfo
    from mcp_servers.llm.ollama_server import OllamaServer
    from mcp_servers.asr.whisperx_server import WhisperXServer
    from orchestrator.state import UnifiedTranscript, TranscriptSegment
    from config.loader import get_asr_config

    out_dir = Path(args.output_dir)

    class _NoOpLLM(LLMEngine):
        """Zero-VRAM stub for Pass 1 — returns empty content without any HTTP/GPU calls."""
        def generate_sync(self, system_prompt, messages, config, task="note_generation") -> LLMResponse:
            return LLMResponse(content="", model="noop", prompt_tokens=0, completion_tokens=0)
        async def generate(self, system_prompt, messages, config) -> LLMResponse:
            return LLMResponse(content="", model="noop", prompt_tokens=0, completion_tokens=0)
        async def generate_stream(self, system_prompt, messages, config):
            return; yield  # empty async generator
        async def get_model_info(self) -> ModelInfo:
            return ModelInfo(model_name="noop", context_window=128000)

    # ── Pass 1: ASR ──────────────────────────────────────────────────────────
    print("=== Pass 1: ASR (WhisperX) ===")
    asr_cfg = get_asr_config()
    asr_engine = WhisperXServer.from_config(asr_cfg)
    set_asr_engine_factory(lambda: asr_engine)
    # No-op LLM: completes the pipeline without loading any model into VRAM.
    # This ensures WhisperX has full GPU access across all samples in Pass 1.
    set_llm_engine_factory(lambda: _NoOpLLM())
    asr_graph = build_graph()

    transcript_cache: dict[str, dict] = {}  # sample_id → {text, segments, mode, audio_duration_ms}

    for i, (audio_path, mode, gold_path) in enumerate(samples, 1):
        sample_id = audio_path.parent.name
        print(f"  [{i}/{len(samples)}] {sample_id} ASR ... ", end="", flush=True)
        from orchestrator.state import DeliveryMethod, EncounterState, RecordingMode
        from config.provider_manager import get_provider_manager
        mgr = get_provider_manager()
        provider_profile = mgr.load_or_default("dr_faraz_rahman")
        recording_mode = RecordingMode.AMBIENT if mode == "ambient" else RecordingMode.DICTATION
        state = EncounterState(
            provider_id=provider_profile.id,
            patient_id=f"patient-{sample_id}",
            provider_profile=provider_profile,
            recording_mode=recording_mode,
            delivery_method=DeliveryMethod.CLIPBOARD,
            audio_file_path=str(audio_path),
        )
        from orchestrator.graph import run_encounter
        try:
            final = run_encounter(asr_graph, state)
            if final.transcript:
                transcript_cache[sample_id] = {
                    "full_text": final.transcript.full_text,
                    "segments": [
                        {"text": s.text, "start_ms": s.start_ms, "end_ms": s.end_ms,
                         "speaker": s.speaker, "confidence": s.confidence}
                        for s in (final.transcript.segments or [])
                    ],
                    "audio_duration_ms": final.transcript.audio_duration_ms,
                    "asr_conf": final.metrics.asr_confidence or 0.0,
                    "pp_corrections": final.metrics.postprocessor_corrections or 0,
                    "errors": final.errors,
                }
                print(f"conf={final.metrics.asr_confidence:.2f} pp={final.metrics.postprocessor_corrections}")
            else:
                transcript_cache[sample_id] = {"full_text": "", "segments": [], "errors": final.errors}
                print(f"FAILED: {final.errors}")
        except Exception as exc:
            transcript_cache[sample_id] = {"full_text": "", "segments": [], "errors": [str(exc)]}
            print(f"FAILED: {exc}")

    # Save transcript cache so it can be reused
    cache_path = out_dir / f"transcript_cache_{args.version}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(transcript_cache, indent=2))
    print(f"  Transcripts saved: {cache_path}")

    # ── Free WhisperX VRAM ───────────────────────────────────────────────────
    print("\nFreeing WhisperX VRAM ...")
    del asr_engine
    torch.cuda.empty_cache()
    import time as _time; _time.sleep(3)  # allow CUDA to fully reclaim

    # ── Pass 2: LLM ──────────────────────────────────────────────────────────
    print(f"\n=== Pass 2: LLM ({model}) ===")

    set_llm_engine_factory(lambda: OllamaServer(model_overrides={"note_generation": model}, keep_alive=0))
    llm_graph = build_graph()

    results = []
    total_t0 = _time.time()
    from output.markdown_writer import write_clinical_note
    from output.comparison_writer import write_comparison
    from orchestrator.state import (
        DeliveryMethod, EncounterState, RecordingMode,
        UnifiedTranscript, TranscriptSegment,
    )
    from config.provider_manager import get_provider_manager
    from orchestrator.graph import run_encounter

    for i, (audio_path, mode, gold_path) in enumerate(samples, 1):
        sample_id = audio_path.parent.name
        gold_str = gold_path.name if gold_path else "no gold"
        print(f"  [{i}/{len(samples)}] {sample_id} LLM ... ", end="", flush=True)
        cached = transcript_cache.get(sample_id, {})
        subfolder = "conversations" if "conversations" in str(audio_path) else "dictation"
        sample_out_dir = out_dir / subfolder / sample_id
        sample_out_dir.mkdir(parents=True, exist_ok=True)
        gold_note = gold_path.read_text() if gold_path else ""

        try:
            mgr = get_provider_manager()
            provider_profile = mgr.load_or_default("dr_faraz_rahman")
            recording_mode = RecordingMode.AMBIENT if mode == "ambient" else RecordingMode.DICTATION

            # Rebuild UnifiedTranscript from cache
            segments = [
                TranscriptSegment(
                    text=s["text"], start_ms=s.get("start_ms", 0), end_ms=s.get("end_ms", 0),
                    speaker=s.get("speaker"), confidence=s.get("confidence") or 1.0,
                )
                for s in cached.get("segments", [])
            ]
            transcript = UnifiedTranscript(
                full_text=cached.get("full_text", ""),
                segments=segments,
            )

            # Preload transcript into state so the pipeline skips ASR
            state = EncounterState(
                provider_id=provider_profile.id,
                patient_id=f"patient-{sample_id}",
                provider_profile=provider_profile,
                recording_mode=recording_mode,
                delivery_method=DeliveryMethod.CLIPBOARD,
                audio_file_path=str(audio_path),
                transcript=transcript,  # pre-loaded → transcribe_node will skip ASR
            )

            t0 = _time.time()
            final = run_encounter(llm_graph, state)
            elapsed = _time.time() - t0

            generated_note = final.final_note.to_text() if final.final_note else ""
            write_clinical_note(final, path=sample_out_dir / f"generated_note_{args.version}.md",
                                version=args.version, sample_id=sample_id)

            # Save standalone transcript from the cached ASR output
            cached_text = cached.get("full_text", "").strip()
            if cached_text:
                (sample_out_dir / f"audio_transcript_{args.version}.txt").write_text(cached_text)

            metrics = {
                "asr_engine": "preloaded",
                "asr_conf": f"{cached.get('asr_conf', 0):.2f}",
                "note_conf": f"{final.metrics.note_confidence:.2f}" if final.metrics.note_confidence else "—",
                "pp_corrections": cached.get("pp_corrections", 0),
                "asr_ms": 0,
                "llm_ms": final.metrics.note_gen_ms or 0,
            }
            overlap = write_comparison(
                path=sample_out_dir / f"comparison_{args.version}.md",
                sample_id=sample_id, generated_note=generated_note,
                gold_note=gold_note,
                transcript=final.transcript.full_text if final.transcript else "",
                metrics=metrics, version=args.version,
            )
            overlap_str = f"{overlap:.0%}" if gold_note else "—"
            print(f"{elapsed:.1f}s | note={final.metrics.note_confidence:.2f} overlap={overlap_str}")
            results.append({
                "id": sample_id, "mode": mode, "audio": audio_path.name,
                "elapsed": elapsed, "asr_ms": 0, "llm_ms": final.metrics.note_gen_ms or 0,
                "asr_engine": "preloaded", "llm_engine": final.llm_engine_used,
                "asr_conf": cached.get("asr_conf", 0.0),
                "note_conf": final.metrics.note_confidence or 0.0,
                "pp_corrections": cached.get("pp_corrections", 0),
                "overlap": overlap, "has_gold": bool(gold_note),
                "errors": final.errors,
                "segments": len(segments),
                "audio_duration_s": (cached.get("audio_duration_ms") or 0) / 1000,
            })
        except Exception as exc:
            import traceback; traceback.print_exc()
            print(f"FAILED: {exc}")
            results.append({
                "id": sample_id, "mode": mode, "audio": audio_path.name,
                "elapsed": 0, "asr_ms": 0, "llm_ms": 0,
                "asr_conf": 0, "note_conf": 0, "pp_corrections": 0,
                "overlap": 0, "has_gold": bool(gold_note), "errors": [str(exc)],
                "segments": 0, "audio_duration_s": 0,
                "asr_engine": "—", "llm_engine": "—",
            })

    return results, _time.time() - total_t0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", help="Pipeline version label (v1, v2, v3)")
    parser.add_argument("--data-dir", default=None,
                        help="Single data dir to scan (default: both data/dictation + data/conversations)")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--model", default=None,
                        help="Ollama model name to use (default: auto-discover first available model)")
    parser.add_argument("--two-pass", action="store_true",
                        help="Two-pass mode: ASR all samples first (frees GPU), then LLM all samples. "
                             "Required for large models (≥14B) on a shared GPU with WhisperX.")
    args = parser.parse_args()

    data_dirs = [args.data_dir] if args.data_dir else _DATA_DIRS
    samples = _collect_samples(data_dirs)

    if not samples:
        print(f"No audio samples found in: {data_dirs}")
        sys.exit(1)

    model = args.model or _discover_ollama_model()
    dictation_count = sum(1 for _, m, _ in samples if m == "dictation")
    ambient_count = sum(1 for _, m, _ in samples if m == "ambient")
    print(f"Ollama model : {model}")
    print(f"Version      : {args.version}")
    print(f"Samples      : {len(samples)} ({dictation_count} dictation, {ambient_count} ambient)")
    print(f"Two-pass     : {'yes' if args.two_pass else 'no'}")
    print()

    if args.two_pass:
        results, total_elapsed = _two_pass_main(args, samples, model)
        write_batch_report(results, model, args.version, total_elapsed, Path(args.output_dir))
        overlaps = [r["overlap"] for r in results if r.get("has_gold") and not r.get("errors")]
        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
        print(f"\n{'─'*70}")
        print(f"Done  : {len(results)} samples in {total_elapsed:.0f}s")
        print(f"Avg overlap : {avg_overlap:.0%}")
        print(f"{'─'*70}")
        return

    from orchestrator.graph import build_graph
    from orchestrator.nodes.note_node import set_llm_engine_factory
    from orchestrator.nodes.transcribe_node import set_asr_engine_factory
    from mcp_servers.llm.ollama_server import OllamaServer
    from mcp_servers.asr.whisperx_server import WhisperXServer
    from config.loader import get_asr_config

    # Create a singleton WhisperXServer so the GPU model is loaded once
    # and reused across all samples — prevents CUDA OOM from accumulating instances.
    asr_cfg = get_asr_config()
    asr_engine = WhisperXServer.from_config(asr_cfg)
    set_asr_engine_factory(lambda: asr_engine)
    # keep_alive=0 unloads the LLM from VRAM after each response so WhisperX
    # can reclaim VRAM for the next sample's ASR pass. Without this, large LLMs
    # (≥14B) cause CUDA OOM on the second sample.
    set_llm_engine_factory(lambda: OllamaServer(model_overrides={"note_generation": model}, keep_alive=0))
    graph = build_graph()

    results = []
    total_t0 = time.time()

    for i, (audio_path, mode, gold_path) in enumerate(samples, 1):
        sample_id = audio_path.parent.name
        gold_str = gold_path.name if gold_path else "no gold"
        print(f"[{i}/{len(samples)}] {sample_id} ({mode}, {audio_path.name}, gold={gold_str}) ... ", end="", flush=True)
        try:
            r = run_sample(audio_path, mode, gold_path, graph, args.version, Path(args.output_dir))
            overlap_str = f"{r['overlap']:.0%}" if r["has_gold"] else "—"
            print(
                f"{r['elapsed']:.1f}s | "
                f"ASR={r['asr_conf']:.2f} note={r['note_conf']:.2f} "
                f"overlap={overlap_str} pp={r['pp_corrections']}"
                + (f" ERRORS: {r['errors']}" if r["errors"] else "")
            )
            results.append(r)
        except Exception as exc:
            import traceback
            print(f"FAILED: {exc}")
            traceback.print_exc()
            results.append({
                "id": sample_id, "mode": mode, "audio": audio_path.name,
                "elapsed": 0, "asr_ms": 0, "llm_ms": 0,
                "asr_conf": 0, "note_conf": 0, "pp_corrections": 0,
                "overlap": 0, "has_gold": gold_path is not None, "errors": [str(exc)],
                "segments": 0, "audio_duration_s": 0,
                "asr_engine": "—", "llm_engine": "—",
            })

    total_elapsed = time.time() - total_t0
    overlaps = [r["overlap"] for r in results if r.get("has_gold") and not r.get("errors")]
    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0

    print(f"\n{'─'*70}")
    print(f"Done  : {len(results)} samples in {total_elapsed:.0f}s")
    print(f"Avg overlap : {avg_overlap:.0%}")
    print(f"{'─'*70}")

    write_batch_report(results, model, args.version, total_elapsed, Path(args.output_dir))

    out_dir = Path(args.output_dir)
    print(f"\nPer-sample files saved to {out_dir}/{{dictation,conversations}}/<sample_id>/:")
    print(f"  generated_note_{args.version}.md")
    print(f"  comparison_{args.version}.md")


if __name__ == "__main__":
    main()
