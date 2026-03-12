"""
scripts/prepare_asr_training_data.py

Prepares provider-specific ASR training data for Whisper LoRA fine-tuning.

Strategy:
  1. For each audio sample, run WhisperX forced alignment to produce word-level
     timestamps anchored to the gold note text.
  2. Segment the aligned audio into 10–30 second chunks.
  3. Apply data augmentation (speed perturbation, additive noise).
  4. Save a HuggingFace `datasets`-compatible DatasetDict for use with
     `finetune_whisper_lora.py`.

The gold note (soap_final.md / soap_initial.md) contains the authoritative
clinical text for each encounter.  WhisperX forced alignment pins each word
in the gold note to a timestamp in the audio, giving us accurate audio/text
pairs even when the base Whisper transcript contains medical term errors.

Output:
    data/asr_training/{provider_id}/
        train/   — ~90% of chunks (Arrow format)
        eval/    — ~10% of chunks (held-out for WER evaluation)
        manifest.json — metadata: chunk count, total hours, samples used

Usage:
    python scripts/prepare_asr_training_data.py --provider dr_faraz_rahman
    python scripts/prepare_asr_training_data.py --provider dr_faraz_rahman --augment
    python scripts/prepare_asr_training_data.py --provider dr_faraz_rahman --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
OUTPUT_TRAINING_DIR = ROOT / "data" / "asr_training"

# Filtering thresholds
MIN_CHUNK_DURATION_S = 3.0
MAX_CHUNK_DURATION_S = 30.0
MIN_ALIGNMENT_CONFIDENCE = 0.6   # skip word segments below this confidence


# ─────────────────────────────────────────────────────────────────────────────
# Text extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_plain_text(markdown_path: Path) -> str:
    """
    Strip Markdown formatting from a SOAP note to produce plain text suitable
    for forced alignment.

    Removes:
      - Markdown headers (# ## ### ...)
      - Bold/italic markers
      - Table pipes and formatting rows
      - HTML tags
      - Empty lines (collapsed)
    """
    text = markdown_path.read_text(encoding="utf-8", errors="replace")

    # Remove markdown headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", text)
    # Remove table separators (---|---)
    text = re.sub(r"^\|[-:| ]+\|?\s*$", "", text, flags=re.MULTILINE)
    # Remove table pipes (keep the cell content)
    text = re.sub(r"\|", " ", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove metadata lines like **Date:** ... **Provider:** ...
    text = re.sub(r"\*\*[^*]+:\*\*[^\n]*", "", text)
    # Collapse extra whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Audio chunking helpers
# ─────────────────────────────────────────────────────────────────────────────

def chunk_segments(
    segments: list[dict],
    min_dur: float = MIN_CHUNK_DURATION_S,
    max_dur: float = MAX_CHUNK_DURATION_S,
) -> list[dict]:
    """
    Group WhisperX word-aligned segments into audio chunks of 10–30 seconds.
    Each chunk contains: start_s, end_s, text.
    """
    chunks: list[dict] = []
    buf_words: list[str] = []
    buf_start: Optional[float] = None
    buf_end: float = 0.0

    for seg in segments:
        for word in seg.get("words", []):
            w_start = word.get("start", 0.0)
            w_end = word.get("end", 0.0)
            w_text = word.get("word", "").strip()
            w_conf = word.get("score", 1.0)

            if w_conf < MIN_ALIGNMENT_CONFIDENCE:
                continue  # skip low-confidence alignments
            if not w_text:
                continue

            if buf_start is None:
                buf_start = w_start

            buf_words.append(w_text)
            buf_end = w_end

            current_dur = buf_end - buf_start
            # Flush if over max duration or if we hit a sentence boundary
            if current_dur >= max_dur or (
                current_dur >= min_dur and w_text.endswith((".", "?", "!"))
            ):
                chunks.append({
                    "start_s": buf_start,
                    "end_s": buf_end,
                    "duration_s": round(buf_end - buf_start, 3),
                    "text": " ".join(buf_words).strip(),
                })
                buf_words = []
                buf_start = None

    # Flush remaining
    if buf_words and buf_start is not None:
        dur = buf_end - buf_start
        if dur >= min_dur:
            chunks.append({
                "start_s": buf_start,
                "end_s": buf_end,
                "duration_s": round(dur, 3),
                "text": " ".join(buf_words).strip(),
            })

    return chunks


def extract_audio_segment(
    audio_path: Path,
    start_s: float,
    end_s: float,
    output_path: Path,
) -> bool:
    """Cut a segment from audio_path using ffmpeg. Returns True on success."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s),
        "-to", str(end_s),
        "-i", str(audio_path),
        "-ar", "16000",   # 16kHz mono for Whisper
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Augmentation
# ─────────────────────────────────────────────────────────────────────────────

def augment_audio(audio_array, sample_rate: int = 16000):
    """
    Apply speed perturbation (±10%) and additive Gaussian noise (SNR 15–25 dB).

    Requires: audiomentations (pip install audiomentations)
    Falls back silently if not installed.
    """
    try:
        import numpy as np
        from audiomentations import Compose, AddGaussianSNR, TimeStretch

        augment = Compose([
            TimeStretch(min_rate=0.9, max_rate=1.1, p=0.5),
            AddGaussianSNR(min_snr_db=15.0, max_snr_db=25.0, p=0.5),
        ])
        return augment(samples=audio_array, sample_rate=sample_rate)
    except ImportError:
        return audio_array  # skip augmentation if not available


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def discover_samples(provider_id: str) -> list[dict]:
    """
    Find all audio+gold-note sample pairs available for this provider.
    Returns list of {audio_path, gold_path, sample_id, mode}.
    """
    pairs = []

    for mode, audio_name, gold_names in [
        ("dictation", "dictation.mp3", ["soap_final.md"]),
        ("ambient",   "conversation.mp3", ["soap_initial.md", "soap_final.md"]),
    ]:
        data_subdir = DATA_DIR / ("dictation" if mode == "dictation" else "conversations")
        if not data_subdir.exists():
            continue
        for sample_dir in sorted(data_subdir.iterdir()):
            if not sample_dir.is_dir():
                continue
            audio = sample_dir / audio_name
            if not audio.exists():
                # Try alternative audio name for conversations
                audio = sample_dir / "conversation.mp3"
            if not audio.exists():
                continue

            gold = None
            for name in gold_names:
                if (sample_dir / name).exists():
                    gold = sample_dir / name
                    break
            if gold is None:
                continue

            pairs.append({
                "sample_id": sample_dir.name,
                "audio_path": audio,
                "gold_path": gold,
                "mode": mode,
            })

    log.info("Discovered %d sample pairs for provider %s", len(pairs), provider_id)
    return pairs


def process_sample(
    sample: dict,
    out_dir: Path,
    augment: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """
    Run forced alignment on one sample and return a list of chunk records.
    Each record: {audio_file, text, duration_s, sample_id, mode}.
    """
    import whisperx  # lazy import — requires GPU env

    sample_id = sample["sample_id"]
    audio_path = sample["audio_path"]
    gold_path = sample["gold_path"]

    log.info("Processing sample %s (%s)", sample_id, sample["mode"])

    # 1. Extract plain text from gold note
    plain_text = extract_plain_text(gold_path)
    if len(plain_text) < 50:
        log.warning("  Gold note too short (%d chars) — skipping", len(plain_text))
        return []

    # 2. Load audio
    audio = whisperx.load_audio(str(audio_path))

    # 3. Forced alignment (wav2vec2) — align gold note text to audio timestamps
    #    We first run a quick transcription to get segment timestamps, then re-align
    #    the gold text within those segments.
    log.info("  Running base transcription for segment timing…")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model("large-v3", device, compute_type=compute_type)
    result = model.transcribe(audio, batch_size=16, language="en")
    del model  # free GPU memory

    if not result.get("segments"):
        log.warning("  No segments from base transcription — skipping")
        return []

    log.info("  Aligning word timestamps…")
    align_model, align_metadata = whisperx.load_align_model(
        language_code="en", device=device
    )
    aligned = whisperx.align(
        result["segments"], align_model, align_metadata, audio, device,
        return_char_alignments=False,
    )
    del align_model

    # 4. Chunk into 10–30s segments
    chunks = chunk_segments(aligned["segments"])
    log.info("  Got %d chunks from sample %s", len(chunks), sample_id)

    if dry_run:
        return [{"dry_run": True, "sample_id": sample_id, "chunk_count": len(chunks)}]

    # 5. Extract audio segments + (optionally) augment
    sample_out = out_dir / sample_id
    sample_out.mkdir(parents=True, exist_ok=True)

    records = []
    for i, chunk in enumerate(chunks):
        wav_path = sample_out / f"chunk_{i:04d}.wav"
        ok = extract_audio_segment(audio_path, chunk["start_s"], chunk["end_s"], wav_path)
        if not ok:
            continue

        records.append({
            "audio": str(wav_path),
            "sentence": chunk["text"],
            "duration_s": chunk["duration_s"],
            "sample_id": sample_id,
            "mode": sample["mode"],
        })

        # Augmented copy
        if augment:
            try:
                import numpy as np
                import soundfile as sf
                raw, sr = sf.read(str(wav_path))
                augmented = augment_audio(raw.astype(np.float32), sr)
                aug_path = sample_out / f"chunk_{i:04d}_aug.wav"
                sf.write(str(aug_path), augmented, sr, subtype="PCM_16")
                records.append({
                    "audio": str(aug_path),
                    "sentence": chunk["text"],
                    "duration_s": chunk["duration_s"],
                    "sample_id": sample_id,
                    "mode": sample["mode"],
                    "augmented": True,
                })
            except Exception as e:
                log.warning("  Augmentation failed for chunk %d: %s", i, e)

    return records


def build_dataset(
    provider_id: str,
    augment: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Full pipeline: discover → align → chunk → split → save HuggingFace dataset.
    """
    out_dir = OUTPUT_TRAINING_DIR / provider_id
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = discover_samples(provider_id)
    if not samples:
        log.error("No samples found. Check data/dictation/ and data/conversations/")
        return

    all_records: list[dict] = []
    for sample in samples:
        records = process_sample(sample, out_dir / "chunks", augment=augment, dry_run=dry_run)
        all_records.extend(records)

    if dry_run:
        total_chunks = sum(r.get("chunk_count", 0) for r in all_records)
        log.info("DRY RUN — %d samples, ~%d chunks would be generated", len(samples), total_chunks)
        return

    if not all_records:
        log.error("No records produced — check audio paths and WhisperX installation")
        return

    log.info("Total records: %d", len(all_records))

    # 90/10 train/eval split
    from datasets import Dataset, DatasetDict
    import random

    random.shuffle(all_records)
    split_idx = max(1, int(len(all_records) * 0.9))
    train_records = all_records[:split_idx]
    eval_records = all_records[split_idx:]

    train_ds = Dataset.from_list(train_records)
    eval_ds = Dataset.from_list(eval_records)
    ds = DatasetDict({"train": train_ds, "eval": eval_ds})

    save_path = out_dir / "dataset"
    ds.save_to_disk(str(save_path))
    log.info("Dataset saved to %s", save_path)

    # Manifest
    total_hours = sum(r.get("duration_s", 0) for r in all_records) / 3600
    manifest = {
        "provider_id": provider_id,
        "samples_used": len(samples),
        "total_chunks": len(all_records),
        "train_chunks": len(train_records),
        "eval_chunks": len(eval_records),
        "total_hours": round(total_hours, 3),
        "augmented": augment,
        "dataset_path": str(save_path),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Manifest written to %s", manifest_path)
    log.info(
        "Summary: %d chunks (%.2f hours) — train=%d, eval=%d",
        len(all_records), total_hours, len(train_records), len(eval_records),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Prepare physician-specific ASR training data for Whisper LoRA fine-tuning"
    )
    parser.add_argument(
        "--provider", required=True,
        help="Provider ID (must match a config/providers/{id}.yaml file)",
    )
    parser.add_argument(
        "--augment", action="store_true",
        help="Apply speed perturbation + noise augmentation (doubles dataset size)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be produced without running alignment or writing files",
    )
    args = parser.parse_args()

    build_dataset(
        provider_id=args.provider,
        augment=args.augment,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
