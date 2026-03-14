# AI Scribe Enterprise

Fully self-hosted, HIPAA-compliant AI medical scribe. Converts doctor-patient
conversations (ambient mode) and physician dictations (dictation mode) into
structured clinical notes — with zero cloud dependencies and zero PHI egress.

**Current quality:** 4.44 / 5.0 across 22 gold-standard encounters
(LLM-as-judge evaluation against hand-authored notes).

---

## Architecture at a Glance

```
AUDIO FILE
    │
    ▼
┌─────────┐   ┌─────────┐   ┌───────────┐   ┌──────┐   ┌────────┐   ┌──────────┐
│ CONTEXT │──►│ CAPTURE │──►│ TRANSCRIBE│──►│ NOTE │──►│ REVIEW │──►│ DELIVERY │
│  NODE   │   │  NODE   │   │   NODE    │   │ NODE │   │  NODE  │   │  NODE    │
└─────────┘   └─────────┘   └───────────┘   └──────┘   └────────┘   └──────────┘
     │                            │                │
  EHR/YAML                  WhisperX +           Ollama +
  patient                   pyannote +           templates +
  context                   12-stage             specialty
                            post-processor       vocab +
                                                 style
```

Every AI component is pluggable — ASR, LLM, EHR adapters, audio processing —
all behind standard interfaces. Swap providers in `config/engines.yaml`; no code
changes required.

---

## Technology Stack (All Self-Hosted)

| Layer | Default | Alternatives |
|-------|---------|-------------|
| ASR (batch) | WhisperX (faster-whisper + pyannote 3.1 + wav2vec2) | NVIDIA Parakeet |
| ASR (streaming) | NVIDIA Nemotron-Speech-Streaming | WhisperX chunked |
| Diarization | pyannote 3.1 | NVIDIA Multitalker-Parakeet |
| Noise suppression | DeepFilterNet | RNNoise, passthrough |
| LLM inference | Ollama (OpenAI-compatible API) | vLLM, SGLang |
| LLM model | Qwen 2.5-14B (Apache 2.0) | Qwen 2.5-32B, Llama 3.1-70B |
| Post-processing | 12-stage rule-based + 98K medical dict | ByT5 ML model (future) |
| Orchestration | LangGraph | — |
| Database | PostgreSQL | — |
| Object storage | MinIO (S3-compatible) | Local filesystem |
| EHR integration | FHIR R4 / HL7v2 / Browser extension | Stub (YAML files) |

**License cost: $0/month.** Every component is open-source with permissive licenses.

---

## Test Dataset

Audio files for testing are available on SharePoint:

**[Download Test Dataset](https://talismansolutionscom.sharepoint.com/:f:/s/ExcelsiaITprojects-AIScribe/IgBCWV3umPwaRowR3nC8dGVGAV5_VlQBAOBqJuDOewniM58?e=s9fYUE)**

The repository includes encounter metadata (patient demographics, gold-standard notes,
encounter details) but **excludes audio files** (`.mp3`) due to size and PHI concerns.
After downloading, place the audio files into their corresponding `ai-scribe-data/`
encounter folders — the folder names in the SharePoint archive match the repo structure.

### Data Directory Layout

```
ai-scribe-data/
├── conversation/                           # Ambient (multi-speaker) encounters
│   └── <physician_id>/
│       └── <patient>_<mrn>_<date>/
│           ├── conversation_audio.mp3      # Doctor-patient conversation (from SharePoint)
│           ├── note_audio.mp3              # Optional: physician dictation after visit
│           ├── final_soap_note.md          # Gold-standard clinical note
│           ├── patient_demographics.json   # Patient name, DOB, sex, MRN
│           └── encounter_details.json      # Visit type, provider, date, mode
│
├── dictation/                              # Single-speaker physician dictations
│   └── <physician_id>/
│       └── <patient>_<mrn>_<date>/
│           ├── dictation.mp3               # Physician dictation audio (from SharePoint)
│           ├── final_soap_note.md          # Gold-standard clinical note
│           ├── patient_demographics.json
│           └── encounter_details.json
```

All paths are configurable via environment variables (see [Configuration](#configuration) below).

---

## Quick Start

```bash
# 1. Install Ollama and pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b

# 2. Install Python dependencies
pip install -e ".[dev]"
# or: uv venv && uv sync

# 3. Set environment variables
cp .env.example .env
# Set HF_TOKEN (required for pyannote diarization)
set -a && source .env && set +a

# 4. Run the pipeline on a single file
python -c "
from orchestrator.graph import build_graph, run_encounter
from orchestrator.state import EncounterState, RecordingMode, DeliveryMethod
from config.provider_manager import get_provider_manager

graph = build_graph()
profile = get_provider_manager().load_or_default('my_provider')
state = EncounterState(
    provider_id=profile.id,
    patient_id='patient-001',
    provider_profile=profile,
    recording_mode=RecordingMode.DICTATION,
    delivery_method=DeliveryMethod.CLIPBOARD,
    audio_file_path='path/to/audio.mp3',
)
result = run_encounter(graph, state)
print(result.final_note.to_text())
"
```

---

## Batch Evaluation

```bash
# Run pipeline on all samples → generated_note_v5.md per sample
python scripts/batch_eval.py --version v5

# Score with LLM-as-judge (6 dimensions) → quality_report_v5.md
python scripts/run_quality_sweep.py --version v5

# Regression tests (assert no quality regression vs baseline)
python -m pytest tests/quality/test_regression.py -v
```

---

## Quality Progress

| Version | What was added | Score |
|---------|---------------|-------|
| v1 (Session 4) | Basic end-to-end pipeline | ~3.5 |
| v2 (Session 5) | Specialty templates + medical vocabulary | 4.32 |
| v3 (Session 7) | EHR context + patient demographics | 4.34 |
| v4 (Session 8) | Provider profiles + style directives + vocab | **4.38** |

Evaluated against 22 hand-authored orthopedic notes using `llama3.1` as judge
across 6 dimensions: medical accuracy, completeness, hallucination-free,
structure compliance, clinical language, readability.

---

## Provider Profiles

Each provider gets a YAML profile in `config/providers/` that controls the
entire pipeline for their encounters:

```yaml
# config/providers/dr_faraz_rahman.yaml
id: dr_faraz_rahman
specialty: orthopedic

template_routing:
  initial_evaluation: ortho_initial_eval   # 12-section H&P
  follow_up:          ortho_follow_up      # 6-section progress note
  default:            ortho_follow_up

style_directives:
  - "Write in third person (e.g. 'The patient presents...')"
  - "Include ROM measurements in degrees"
  - "Mirror Assessment numbering in the Plan"
  # ... (10 total)

custom_vocabulary:
  - "Spurling"
  - "paralumbar"
  - "WAD"
  # ... (22 terms total)
```

Quality scores are automatically updated after every evaluation sweep.

---

## Infrastructure Sizing

| Tier | Cost | GPU | Capacity |
|------|------|-----|----------|
| Proof of concept | ~$260/mo | 1× T4 16GB | 20–30 notes/day |
| **Production start** ★ | **~$630/mo** | **T4 + A10 24GB** | **100+ notes/day** |
| Quality maximum | ~$1,250/mo | T4 + A100 40GB | 500+ notes/day |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/implementation.md](docs/implementation.md) | **Full implementation reference** — pipeline internals, MCP servers, prompt assembly, provider profiles, quality framework, data flow end-to-end |
| [docs/architecture.md](docs/architecture.md) | System design spec — design principles, component inventory, routing logic, learning service |
| [CLAUDE.md](CLAUDE.md) | Build sequence and session-by-session instructions for Claude Code |

---

## License

Proprietary. All third-party components are open-source:
- WhisperX, faster-whisper, pyannote: MIT / CC-BY-4.0
- OpenMedSpel (98K medical wordlist): GPL 3.0
- LangGraph, LangChain: MIT
- Qwen 2.5: Apache 2.0
- Llama 3.1: Llama Community License
- Ollama, vLLM: MIT / Apache 2.0
