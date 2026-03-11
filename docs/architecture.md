# AI Scribe — System Architecture v2.0

## 1. Design Principles

**P1: Plug-and-play everywhere.** Every intelligence layer — ASR, diarization, noise suppression, LLM, coding engine — is behind a standard interface (MCP tool server). Swapping providers is a config change, never a code change.

**P2: Self-hosted first, cloud-optional.** The default stack runs entirely on your own infrastructure. PHI never leaves your environment. HIPAA compliance is structural, not contractual. Cloud APIs (Deepgram, Claude, AWS) can be added later as additional MCP tool servers through the same interfaces.

**P3: Provider profiles govern everything.** Each clinician has a profile that controls which engines are used, which templates apply, what style the notes follow, and how aggressively corrections are applied. The system tunes itself per-provider over time.

**P4: Every correction is training data.** When a provider edits a generated note, the diff is captured as a labeled training pair. This feeds ASR post-processing refinement, LLM prompt tuning, template evolution, and eventually LoRA fine-tuning of the local LLM.

**P5: Timestamps are sacred.** Every word, speaker turn, mode switch, and addendum is anchored to a millisecond-precise timeline. This enables evidence-linked citations, audit trails, and faithful reconstruction.

**P6: LangGraph orchestrates, MCP connects tools, A2A connects agents.** The encounter pipeline is a state graph (LangGraph). Each node connects to its tools via MCP servers. Services communicate via A2A protocol for future interoperability.

---

## 2. Technology Stack (All Self-Hosted)

### 2.1 Complete Component Inventory

```
LAYER              COMPONENT                    LICENSE          ROLE
─────────────────────────────────────────────────────────────────────────────
AUDIO              DeepFilterNet                MIT              Noise suppression
                   Silero VAD                   MIT              Voice activity detection
                   FFmpeg                       LGPL 2.1         Audio format conversion

ASR (Batch)        WhisperX                     MIT              Primary ASR engine
                     faster-whisper             MIT              CTranslate2 optimized Whisper
                     pyannote 3.1               MIT/CC-BY-4.0    Speaker diarization
                     wav2vec2                   MIT              Word-level alignment

ASR (Streaming)    Nemotron-Speech-Streaming     CC-BY-4.0        Real-time transcription
                   Multitalker-Parakeet         CC-BY-4.0        Multi-speaker streaming

Post-Processing    medasr_postprocessor.py      Proprietary      12-stage rule-based cleanup
                   OpenMedSpel (98K terms)      GPL 3.0          Medical dictionary
                   ByT5 ML model (future)       Proprietary      Learned correction model

LLM                Qwen 2.5 (14B/32B/72B)      Apache 2.0       Note generation, coding, summaries
                   Llama 3.1 (8B/70B)          Llama License    Alternative LLM
                   Mistral (7B/24B)            Apache 2.0       Lightweight alternative

INFERENCE          Ollama                       MIT              Default model serving (dev + prod)
                   vLLM                         Apache 2.0       High-throughput alternative

ORCHESTRATION      LangGraph                    MIT              Pipeline state graph
                   LangChain                    MIT              Tool/chain abstractions

DATA               PostgreSQL                   PostgreSQL Lic   Encounters, profiles, metrics
                   MinIO                        AGPL 3.0         Audio/file object storage
                   Valkey (Redis fork)          BSD              Message queue, session state, cache

WEB                Next.js                      MIT              Web app + review UI
                   Chrome Extension MV3         —                EHR Super Fill + voice nav

MONITORING         Grafana + Prometheus          AGPL/Apache      Metrics and dashboards

TOTAL LICENSE COST: $0/month
```

### 2.2 Infrastructure Tiers

```
TIER 1 — Proof of Concept ($260/mo)
  1x T4 16GB GPU    — WhisperX (ASR) + Qwen 2.5-14B (LLM, time-shared)
  1x CPU instance    — App server, PostgreSQL, MinIO, Valkey
  Capacity:          ~20-30 notes/day
  Note quality:      Acceptable for simple SOAP notes

TIER 2 — Production Start ($630/mo)  ★ RECOMMENDED
  1x T4 16GB GPU    — WhisperX (ASR + diarization)
  1x A10 24GB GPU   — Qwen 2.5-32B via Ollama (LLM)
  1x CPU instance    — App server, PostgreSQL, MinIO, Valkey
  Capacity:          100+ notes/day
  Note quality:      Good across most specialties

TIER 3 — Quality Maximum ($1,250/mo)
  1x T4 16GB GPU    — WhisperX + NeMo Streaming (dual ASR)
  1x A100 40GB GPU  — Qwen 2.5-72B or Llama 70B via vLLM
  2x CPU instances   — App servers, DB cluster
  Capacity:          500+ notes/day
  Note quality:      Rivals Claude/GPT-4o on clinical notes
```

---

## 3. Encounter Pipeline (LangGraph State Graph)

### 3.1 Top-Level Graph

```
                     ENCOUNTER STATE GRAPH (LangGraph)

  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ CONTEXT  │────>│ CAPTURE  │────>│TRANSCRIBE│────>│   NOTE   │
  │  NODE    │     │  NODE    │     │  NODE    │     │   NODE   │
  └──────────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
                        │                │                │
                   [mode router]    [ASR router]    [parallel branch]
                   ambient/dictate  engine select   note+coding+summary
                        │                │                │
                        │           [confidence]          │
                        │            router              │
                        │           pass/retry            │
                        │                │                │
                   ┌────┴────┐     ┌────┴─────┐    ┌────┴─────┐
                   │  PAUSED │     │ RE-ROUTE │    │  REVIEW  │
                   │  (opt)  │     │ (fallback│    │  (HITL)  │
                   └─────────┘     │  engine) │    └────┬─────┘
                                   └──────────┘         │
                                                   ┌────┴─────┐
                                                   │ DELIVER  │
                                                   │  NODE    │
                                                   └────┬─────┘
                                                        │
                                                   ┌────┴─────┐
                                                   │ FEEDBACK │
                                                   │  NODE    │
                                                   └──────────┘
```

### 3.2 Session State Schema

The state object flows through every node, accumulating data at each stage:

```python
from pydantic import BaseModel
from typing import Optional
from enum import Enum

class EncounterState(BaseModel):
    # Identity
    encounter_id: str
    provider_id: str
    patient_id: str
    state: str  # CREATED|CONTEXT_LOADING|READY|CAPTURING|PROCESSING|REVIEWING|DELIVERED

    # Provider profile (loaded at start)
    provider_profile: ProviderProfile

    # Pre-encounter context
    context_packet: Optional[ContextPacket] = None

    # Audio capture
    audio_segments: list[AudioSegment] = []
    mode_events: list[ModeEvent] = []          # ambient/dictation switches
    voice_commands: list[VoiceCommand] = []
    typed_addendums: list[Addendum] = []

    # Transcription
    transcript: Optional[UnifiedTranscript] = None
    asr_engine_used: str = ""
    diarization_engine_used: str = ""
    postprocessor_version: str = ""
    postprocessor_metrics: dict = {}

    # Note generation
    generated_note: Optional[ClinicalNote] = None
    coding_suggestions: list[CodingSuggestion] = []
    patient_summary: Optional[PatientSummary] = None
    llm_engine_used: str = ""
    template_used: str = ""

    # Review
    corrections: list[Correction] = []
    final_note: Optional[ClinicalNote] = None

    # Delivery
    delivery_method: str = ""        # extension|fhir|clipboard
    delivery_result: Optional[dict] = None

    # Quality metrics (accumulated throughout)
    metrics: EncounterMetrics = EncounterMetrics()
```

### 3.3 Node Detail: Pre-Processing → Core → Post-Processing

Every node is itself a sub-graph with pre-processing, core execution, and post-processing steps. Each step is independently skippable, retriable, and swappable.

#### CONTEXT NODE
```
PRE:   validate_patient_id → check_ehr_connectivity → load_provider_profile → dedup_session
CORE:  fetch_ehr_data (via MCP EHR tool server)
POST:  check_completeness → optimize_context_size → minimize_phi → snapshot_context
```

#### CAPTURE NODE
```
PRE:   detect_audio_source → normalize_sample_rate → suppress_noise → normalize_gain
       → detect_voice_activity → score_audio_quality
CORE:  stream_and_buffer (chunked audio capture)
POST:  tag_chunk_metadata → detect_commands → merge_addendums → manage_offline_buffer
       → archive_audio
```

#### TRANSCRIBE NODE
```
PRE:   asr_router (CONDITIONAL EDGE: selects engine) → build_engine_config
       → inject_custom_vocab → convert_audio_format → select_batch_strategy
CORE:  transcribe (via MCP ASR tool server — WhisperX or NeMo or others)
POST:  normalize_transcript → align_diarization
       → POST-PROCESSOR SUB-GRAPH:
           ├── RULES PATH: stages 1-12 (our medasr_postprocessor.py)
           ├── ML PATH: ByT5 model (when trained)
           └── CONFIDENCE COMPARE: pick winner or flag for review
       → score_confidence → update_audio_index → quality_gate
       (quality_gate CONDITIONAL EDGE: pass → continue | fail → re-route to alt engine)
```

#### NOTE NODE
```
PRE:   assemble_prompt → select_template → inject_style_directives
       → structure_by_mode → budget_context_window → prepare_citations
CORE:  PARALLEL BRANCHES (via MCP LLM tool server — Ollama endpoint):
         ├── generate_note (SOAP/H&P/Progress)
         ├── generate_coding (E&M, HCC, CPT)
         └── generate_patient_summary (5th-grade reading level)
POST:  detect_hallucinations → validate_medical_terms (98K dict)
       → link_citations → validate_coding → enforce_style
       → check_readability → check_completeness → score_confidence
```

#### REVIEW NODE
```
PRE:   render_for_editor → highlight_low_confidence → prepare_diff → preload_audio_clips
CORE:  human_review (HITL — waits for provider approval)
POST:  capture_corrections → classify_corrections (ASR_ERROR|STYLE|CONTENT|CODING|TEMPLATE)
       → generate_training_pairs → update_style_model → refine_template → log_quality
```

#### DELIVERY NODE
```
PRE:   map_ehr_fields → convert_format → select_delivery_method → tag_phi_audit
CORE:  push_to_ehr (via MCP EHR tool server or browser extension)
POST:  confirm_delivery → write_audit_log → apply_retention_policy
       → finalize_encounter → emit_quality_metrics
```

---

## 4. MCP Tool Servers (Plug-and-Play Layer)

Every external capability is wrapped in an MCP server with a standard interface. The LangGraph nodes call tools via MCP — they never call engines directly.

### 4.1 ASR MCP Servers

```
mcp_servers/asr/
├── whisperx_server.py          # WhisperX (faster-whisper + pyannote + wav2vec2)
├── nemo_streaming_server.py    # NVIDIA Nemotron-Speech-Streaming
├── nemo_multitalker_server.py  # NVIDIA Multitalker-Parakeet-Streaming
├── deepgram_server.py          # Deepgram Nova-3 Medical (future cloud option)
├── aws_transcribe_server.py    # AWS Transcribe Medical (future cloud option)
└── base.py                     # Common ASREngine interface

# Interface (all servers implement this):
tools:
  - transcribe_batch(audio_path, config) → RawTranscript
  - transcribe_stream(audio_chunk, session) → PartialTranscript
  - get_capabilities() → {streaming, diarization, medical_vocab, max_speakers}
```

### 4.2 LLM MCP Servers

```
mcp_servers/llm/
├── ollama_server.py            # Ollama (default — dev + prod)
├── vllm_server.py              # vLLM (high-throughput production)
├── claude_server.py            # Anthropic Claude (future cloud option)
├── openai_server.py            # OpenAI GPT-4o (future cloud option)
└── base.py                     # Common LLMEngine interface

# Interface (all servers implement this):
tools:
  - generate(system_prompt, messages, config) → LLMResponse
  - generate_stream(system_prompt, messages, config) → AsyncIterator[LLMChunk]
  - get_model_info() → {model_name, context_window, capabilities}

# The Ollama server simply proxies to Ollama's OpenAI-compatible API:
#   http://localhost:11434/v1/chat/completions
# vLLM, Claude, OpenAI all expose the same /v1/chat/completions endpoint.
# Switching between them is a URL + API key config change.
```

### 4.3 EHR MCP Servers

```
mcp_servers/ehr/
├── fhir_server.py              # FHIR R4 (Epic, Cerner, Athena)
├── hl7v2_server.py             # HL7v2 (legacy systems)
├── extension_scrape_server.py  # Browser extension DOM scraping
├── manual_server.py            # Manual entry (provider types context)
└── base.py                     # Common EHRAdapter interface

# Interface:
tools:
  # READ (pre-encounter context)
  - get_patient(identifier) → PatientDemographics
  - get_problem_list(patient_id) → Problem[]
  - get_medications(patient_id) → Medication[]
  - get_allergies(patient_id) → Allergy[]
  - get_recent_labs(patient_id, days) → LabResult[]
  - get_last_visit_note(patient_id) → ClinicalNote

  # WRITE (post-encounter delivery)
  - push_note(patient_id, note) → PushResult
  - push_order(patient_id, order) → PushResult

  # NAVIGATE (voice commands)
  - navigate(command) → NavigationResult
```

### 4.4 Audio Processing MCP Servers

```
mcp_servers/audio/
├── deepfilternet_server.py     # DeepFilterNet noise suppression
├── rnnoise_server.py           # RNNoise (lighter alternative)
├── silero_vad_server.py        # Silero Voice Activity Detection
├── ffmpeg_server.py            # Audio format conversion + resampling
└── base.py                     # Common AudioProcessor interface

# Interface:
tools:
  - suppress_noise(audio, aggressiveness) → CleanedAudio
  - detect_voice_activity(audio, sensitivity) → VADSegments
  - convert_format(audio, target_format, sample_rate) → ConvertedAudio
  - estimate_snr(audio) → QualityScore
```

### 4.5 Data/Reference MCP Servers

```
mcp_servers/data/
├── medical_dict_server.py      # 98K OpenMedSpel + custom vocabulary
├── icd10_server.py             # ICD-10 code lookup
├── cpt_server.py               # CPT code lookup
├── drug_db_server.py           # Drug name/interaction database
├── template_server.py          # Note templates (SOAP, H&P, specialty-specific)
└── base.py                     # Common interface

# Interface:
tools:
  - lookup_medical_term(term) → {found, suggestions}
  - lookup_icd10(description) → ICD10Code[]
  - lookup_cpt(procedure) → CPTCode[]
  - lookup_drug(name) → DrugInfo
  - get_template(specialty, note_type) → NoteTemplate
  - get_custom_vocabulary(provider_id) → string[]
```

---

## 5. Engine Registry and Routing

### 5.1 Engine Registry

All MCP servers register with the Engine Registry at startup. The registry tracks health, capabilities, and quality metrics.

```python
class EngineRegistry:
    engines: dict[EngineType, list[RegisteredEngine]]

    def register(type, name, mcp_server_url, capabilities, config)
    def select(type, provider_profile, context) → SelectedEngine
    def select_with_fallback(type, provider_profile) → list[SelectedEngine]
    def health_check(type, name) → HealthStatus
    def record_quality(type, name, provider_id, score)
    def get_quality_scores(type, provider_id) → dict[engine_name, score]
```

### 5.2 ASR Router Decision Logic

```python
def select_asr_engine(profile, audio_meta, registry):
    # 1. Provider override?
    if profile.asr_override:
        return registry.get(profile.asr_override)

    # 2. A/B test assignment?
    if ab_test.is_active(profile):
        return ab_test.get_assignment(profile)

    # 3. Capability filter
    candidates = registry.get_healthy("asr")
    if audio_meta.mode == "ambient" and audio_meta.speakers > 1:
        candidates = [e for e in candidates if e.supports_diarization]
    if audio_meta.needs_streaming:
        candidates = [e for e in candidates if e.supports_streaming]

    # 4. Score by historical quality for this provider
    scored = [(e, registry.get_quality(e, profile.id)) for e in candidates]
    scored.sort(key=lambda x: -x[1])

    return EngineSelection(
        primary=scored[0][0],
        fallback=scored[1][0] if len(scored) > 1 else None,
    )
```

### 5.3 LLM Router Decision Logic

```python
def select_llm_engine(profile, task, registry):
    # Task-based selection (different tasks may use different models)
    # e.g., note_generation → 32B model, patient_summary → 14B model
    candidates = registry.get_healthy("llm")

    # Provider override?
    if profile.llm_override:
        return registry.get(profile.llm_override)

    # Task-based default
    task_defaults = {
        "note_generation": "qwen2.5:32b",    # needs quality
        "coding":          "qwen2.5:32b",    # needs medical knowledge
        "patient_summary": "qwen2.5:14b",    # can use smaller model
        "command_parse":   "qwen2.5:7b",     # fast, simple task
    }

    model = task_defaults.get(task, "qwen2.5:32b")
    return registry.select("llm", model_name=model)
```

---

## 6. Plug-and-Play Configuration

### 6.1 Inference Endpoints (Ollama Default)

```yaml
# config/engines.yaml

llm:
  default_server: ollama
  servers:
    ollama:
      type: ollama
      url: "http://localhost:11434/v1"
      models:
        note_generation: "qwen2.5:32b"
        coding: "qwen2.5:32b"
        patient_summary: "qwen2.5:14b"
        command_parse: "qwen2.5:7b"

    vllm:  # swap in for production throughput
      type: vllm
      url: "http://localhost:8000/v1"
      models:
        note_generation: "Qwen/Qwen2.5-32B-Instruct-AWQ"

    claude:  # future cloud option
      type: openai_compatible
      url: "https://api.anthropic.com/v1"
      api_key_env: "ANTHROPIC_API_KEY"
      models:
        note_generation: "claude-sonnet-4-20250514"

asr:
  default_server: whisperx
  servers:
    whisperx:
      type: whisperx
      model: "large-v3"
      device: "cuda"
      compute_type: "float16"
      diarization: true
      hf_token_env: "HF_TOKEN"

    nemo_streaming:
      type: nemo
      model: "nvidia/nemotron-speech-streaming-en-0.6b"
      device: "cuda"
      streaming: true

    nemo_multitalker:
      type: nemo_multitalker
      model: "nvidia/multitalker-parakeet-streaming-0.6b-v1"
      device: "cuda"
      streaming: true
      max_speakers: 5

    deepgram:  # future cloud option
      type: deepgram
      api_key_env: "DEEPGRAM_API_KEY"
      model: "nova-3-medical"

audio_processing:
  noise_suppression:
    default: deepfilternet
    options: [deepfilternet, rnnoise, passthrough]
  vad:
    default: silero
    sensitivity: 0.5

ehr:
  default_adapter: manual
  adapters:
    manual:
      type: manual
    extension:
      type: browser_extension
    fhir:
      type: fhir
      base_url_env: "FHIR_BASE_URL"

post_processing:
  mode: hybrid  # rules_only | ml_only | hybrid
  rules_pipeline: true
  ml_model_path: null  # populated after training
  medical_wordlist: "./data/medical_wordlist.txt"
  confidence_threshold: 0.85
```

### 6.2 Provider Profile

```yaml
# Each provider gets a profile that tunes the entire pipeline

provider:
  id: "dr-smith-001"
  name: "Dr. Sarah Smith"
  specialty: "orthopedic"
  npi: "1234567890"

  # Note preferences
  note_format: "SOAP"
  template: "ortho_followup_v3"
  style_directives:
    - "Use active voice"
    - "Spell out medication names fully"
    - "Include ROM in degrees"
    - "Always document neurovascular status"
  custom_vocabulary:
    - "Dr. Ramirez"
    - "St. Luke's Medical Center"
    - "Medrol Dosepak"
    - "Spurling's maneuver"

  # Engine overrides (null = use defaults from engines.yaml)
  asr_engine: null        # auto-select via router
  llm_engine: null        # auto-select via router
  noise_suppression: "aggressive"
  postprocessor_mode: "hybrid"

  # Learned (updated by feedback loop)
  style_model_version: "v0"
  correction_count: 0
  quality_scores:
    whisperx: 0.85
    nemo_streaming: null  # not yet tested
```

---

## 7. Feature → Component Traceability

```
FEATURE (from requirements)              PIPELINE COMPONENTS                 PHASE
──────────────────────────────────────────────────────────────────────────────────
P0 Multi-Speaker Diarization (N=5)       Capture.audio_capture               1
                                         Transcribe.asr_router
                                         Transcribe.whisperx (pyannote)
                                         Transcribe.nemo_multitalker (P2)

P0 Background Noise Suppression          Capture.suppress_noise              1
                                         (MCP: deepfilternet_server)

P0 Hybrid Ambient/Dictation Toggle       Capture.mode_controller             1
                                         Orchestrator.session_state
                                         Note.structure_by_mode

P0 EHR "Super Fill" / Extension          Delivery.browser_extension          1
                                         Delivery.map_ehr_fields
                                         (MCP: extension_scrape_server)

P0 Offline Audio Buffering               Capture.offline_buffer (IndexedDB)  1
                                         Delivery.sync_engine

P1 Evidence-Linked Citations             Transcribe.audio_indexer            2
                                         Note.prepare_citations
                                         Note.link_citations
                                         Review.preload_audio_clips

P1 Self-Learning Personalization         Review.capture_corrections          2
                                         Review.update_style_model
                                         Feedback.generate_training_pairs
                                         Note.inject_style_directives

P1 Specialty Context-Pull                Context.fetch_ehr_data              2
                                         Context.context_assembler
                                         (MCP: fhir_server)
                                         Note.assemble_prompt

P1 Voice EHR Navigation                  Capture.command_detector            2
                                         (MCP: extension_scrape_server)
                                         Orchestrator.route_command

P2 E&M / HCC Coding Prompts             Note.generate_coding (parallel)     3
                                         Note.validate_coding
                                         (MCP: icd10_server, cpt_server)

P2 Patient-Language Summary              Note.generate_patient_summary       3
                                         Note.check_readability

P3 Silent Mid-Visit Addendum             Capture.input_merger                3
                                         Orchestrator.merge_addendum
                                         Note.assemble_prompt (includes addendums)
```

---

## 8. Data Model

### 8.1 Core Entities

```
Encounter {
  id, provider_id, patient_id, state, created_at, completed_at
  context_packet, audio_segments[], mode_events[], typed_addendums[]
  transcript (UnifiedTranscript), asr_engine_used, postprocessor_metrics
  generated_note (ClinicalNote), coding_suggestions[], patient_summary
  corrections[], final_note, delivery_result, metrics
}

ProviderProfile {
  id, name, specialty, npi, practice_id
  note_format, template_id, style_directives[], custom_vocabulary[]
  asr_override, llm_override, noise_suppression_level
  style_model_version, correction_history, quality_scores{}
}

UnifiedTranscript {
  segments: [{text, speaker, start_ms, end_ms, confidence,
              words: [{text, start_ms, end_ms, conf}],
              mode: ambient|dictation, source: asr|typed_addendum}]
  engine_used, diarization_engine, audio_duration_ms
}

ClinicalNote {
  sections: [{type, content, citations: [{note_range, transcript_segment_id,
              audio_start_ms, audio_end_ms, confidence}]}]
  metadata: {generated_at, llm_used, template_used, confidence_score}
}

AudioSegment {
  id, encounter_id, sequence_number, start_ms, end_ms
  mode, storage_path, sample_rate, snr_estimate
}
```

### 8.2 Storage

```
PostgreSQL     — Encounters, provider profiles, quality metrics, corrections
MinIO (S3)     — Audio segments (encrypted at rest, lifecycle policies)
Valkey (Redis) — Session state, event bus, LangGraph checkpoints, cache
File system    — Model weights (Ollama manages), templates, dictionaries
```

---

## 9. Learning Service (Continuous Improvement)

### 9.1 Correction Flow

```
Provider edits note in Review UI
    │
    ├── Diff computed: original AI output vs provider edit
    │
    ├── Classification:
    │   ├── ASR_ERROR:  "naproxen" was "nap rocks in" → ASR training data
    │   ├── STYLE:      AI wrote passive, provider wants active → style model update
    │   ├── CONTENT:    AI missed a finding → prompt tuning
    │   ├── CODING:     Wrong E&M level → coding model feedback
    │   └── TEMPLATE:   Provider always adds a section → template refinement
    │
    ├── ASR corrections → post-processor training pairs (our existing pipeline)
    ├── Style corrections → provider profile style_directives update
    ├── Content corrections → prompt library refinement
    └── All corrections → (transcript, approved_note) pairs for future LoRA fine-tuning
```

### 9.2 Retraining Triggers

```
ASR Post-Processor:   Every 100 ASR corrections → retrain ByT5 model
LLM Fine-Tuning:      Every 1000 approved notes → LoRA fine-tune Qwen on your data
Template Evolution:    Every 50 template corrections per provider → suggest template update
Engine Quality:        Continuous → update quality scores in provider profile
A/B Tests:            Per-provider, per-encounter assignment → statistical graduation
```

---

## 10. Implementation Phases

```
PHASE 1 — MVP (Weeks 1-8)
  Core pipeline: Capture → Transcribe → Note → Clipboard/Manual Copy
  • WhisperX on T4 (batch mode, process after encounter ends)
  • Qwen 2.5-32B on A10 via Ollama
  • LangGraph pipeline with 6 nodes
  • Basic web app: start/stop recording, review/edit note, copy to clipboard
  • Our 12-stage post-processor for transcript cleanup
  • Single SOAP template
  • Provider profiles (basic: name, specialty, custom vocabulary)
  • PostgreSQL + MinIO + Valkey setup
  MCP servers: whisperx, ollama_llm, medical_dict, template, manual_ehr

PHASE 2 — Competitive (Weeks 9-16)
  Multi-engine + EHR integration + citations
  • Browser extension (Super Fill for top 3 web-based EHRs)
  • Hybrid ambient/dictation toggle with mode controller
  • Offline audio buffering + sync
  • DeepFilterNet noise suppression
  • Evidence-linked citations (audio playback from note sentences)
  • NeMo Streaming as second ASR engine + ASR Router
  • Context assembly (manual patient context entry initially)
  • Self-learning: correction capture + style model updates
  ADD MCP servers: nemo_streaming, deepfilternet, extension_scrape_ehr

PHASE 3 — Differentiation (Weeks 17-24)
  Intelligence + learning + coding
  • Coding suggestions (E&M, HCC, CPT)
  • Patient-language summaries
  • Voice command detection (basic set)
  • ByT5 ML post-processor (trained on accumulated corrections)
  • A/B testing framework for engines
  • FHIR adapter for 1-2 EHRs (context pull)
  • LoRA fine-tuning of LLM on accumulated notes
  ADD MCP servers: icd10, cpt, drug_db, fhir_ehr, command_detector

PHASE 4 — Scale (Weeks 25+)
  • Additional EHR adapters
  • Mobile app (React Native / PWA)
  • Silent mid-visit addendum
  • Voice EHR navigation (full command set)
  • Continuous retraining automation
  • Multi-tenant, multi-practice support
  • Optional cloud API engines via same MCP interfaces
```

---

## 11. Claude Code Project Structure

```
ai-scribe/
│
├── README.md
├── docker-compose.yml              # Full stack: app + GPUs + DBs
├── config/
│   ├── engines.yaml                # Engine configuration (§6.1)
│   ├── templates/                  # Note templates by specialty
│   │   ├── soap_default.yaml
│   │   ├── ortho_followup.yaml
│   │   ├── psych_progress.yaml
│   │   └── peds_wellchild.yaml
│   └── prompts/                    # LLM prompt library
│       ├── note_generation.yaml
│       ├── coding_suggestion.yaml
│       └── patient_summary.yaml
│
├── orchestrator/                   # LangGraph encounter pipeline
│   ├── __init__.py
│   ├── graph.py                    # Top-level encounter graph definition
│   ├── state.py                    # EncounterState Pydantic schema
│   ├── nodes/                      # Each pipeline stage
│   │   ├── __init__.py
│   │   ├── context_node.py         # Pre-encounter context assembly
│   │   ├── capture_node.py         # Audio capture + preprocessing
│   │   ├── transcribe_node.py      # ASR + diarization + post-processing
│   │   ├── note_node.py            # LLM note generation + coding + summary
│   │   ├── review_node.py          # HITL review + correction capture
│   │   └── delivery_node.py        # EHR push + finalization
│   ├── edges/                      # Conditional routing logic
│   │   ├── __init__.py
│   │   ├── asr_router.py           # ASR engine selection
│   │   ├── llm_router.py           # LLM engine selection
│   │   ├── mode_router.py          # Ambient/dictation routing
│   │   ├── confidence_router.py    # Quality gate: pass/retry/flag
│   │   └── delivery_router.py      # Extension/FHIR/clipboard selection
│   └── subgraphs/                  # Sub-graphs within nodes
│       ├── __init__.py
│       ├── postprocessor_graph.py  # Rules vs ML vs hybrid routing
│       └── note_parallel_graph.py  # Parallel: note + coding + summary
│
├── mcp_servers/                    # Plug-and-play tool servers
│   ├── __init__.py
│   ├── base.py                     # Base MCP server class
│   ├── registry.py                 # Engine registry + health checks
│   │
│   ├── asr/                        # ASR engine adapters
│   │   ├── __init__.py
│   │   ├── base.py                 # ASREngine interface
│   │   ├── whisperx_server.py
│   │   ├── nemo_streaming_server.py
│   │   ├── nemo_multitalker_server.py
│   │   ├── deepgram_server.py      # Future cloud option
│   │   └── aws_transcribe_server.py # Future cloud option
│   │
│   ├── llm/                        # LLM engine adapters
│   │   ├── __init__.py
│   │   ├── base.py                 # LLMEngine interface
│   │   ├── ollama_server.py        # DEFAULT — Ollama OpenAI-compat API
│   │   ├── vllm_server.py          # High-throughput alternative
│   │   ├── claude_server.py        # Future cloud option
│   │   └── openai_server.py        # Future cloud option
│   │
│   ├── ehr/                        # EHR adapters
│   │   ├── __init__.py
│   │   ├── base.py                 # EHRAdapter interface
│   │   ├── fhir_server.py
│   │   ├── hl7v2_server.py
│   │   ├── extension_server.py     # Browser extension bridge
│   │   └── manual_server.py
│   │
│   ├── audio/                      # Audio processing
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── deepfilternet_server.py
│   │   ├── silero_vad_server.py
│   │   └── ffmpeg_server.py
│   │
│   └── data/                       # Reference data
│       ├── __init__.py
│       ├── medical_dict_server.py
│       ├── icd10_server.py
│       ├── cpt_server.py
│       ├── drug_db_server.py
│       └── template_server.py
│
├── postprocessor/                  # Our ASR post-processing pipeline
│   ├── __init__.py
│   ├── medasr_postprocessor.py     # 12-stage rule-based pipeline
│   ├── medical_wordlist.txt        # 98K OpenMedSpel dictionary
│   └── ml/                         # ML post-processor
│       ├── generate_training_data.py
│       ├── train_model.py
│       ├── inference.py
│       └── evaluate.py
│
├── learning/                       # Continuous improvement
│   ├── __init__.py
│   ├── correction_capture.py       # Diff computation + classification
│   ├── training_pair_generator.py  # Corrections → training data
│   ├── style_model.py              # Per-provider style learning
│   ├── quality_monitor.py          # Engine quality tracking
│   ├── ab_test.py                  # A/B test framework
│   └── retrain_trigger.py          # Automated retraining orchestration
│
├── api/                            # Backend API (FastAPI)
│   ├── __init__.py
│   ├── main.py                     # FastAPI app + WebSocket
│   ├── routes/
│   │   ├── encounters.py           # Encounter CRUD + lifecycle
│   │   ├── providers.py            # Provider profile management
│   │   ├── audio.py                # Audio upload + streaming endpoints
│   │   ├── notes.py                # Note retrieval + editing
│   │   └── webhooks.py             # Browser extension communication
│   ├── middleware/
│   │   ├── auth.py                 # JWT authentication
│   │   ├── audit.py                # HIPAA audit logging
│   │   └── rate_limit.py
│   └── ws/
│       ├── audio_stream.py         # WebSocket for live audio
│       └── session_events.py       # WebSocket for session state updates
│
├── client/                         # Frontend
│   ├── web/                        # Next.js web application
│   │   ├── package.json
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx            # Dashboard
│   │   │   ├── encounter/
│   │   │   │   ├── [id]/
│   │   │   │   │   ├── capture.tsx # Live recording UI
│   │   │   │   │   ├── review.tsx  # Note review + editing
│   │   │   │   │   └── transcript.tsx # Transcript viewer + audio playback
│   │   │   ├── providers/
│   │   │   │   └── [id]/settings.tsx # Provider profile management
│   │   │   └── admin/
│   │   │       ├── engines.tsx     # Engine configuration UI
│   │   │       └── quality.tsx     # Quality dashboard
│   │   └── components/
│   │       ├── NoteEditor.tsx      # Rich text note editor with citations
│   │       ├── TranscriptViewer.tsx # Speaker-labeled transcript
│   │       ├── AudioPlayer.tsx     # Citation-linked audio playback
│   │       ├── RecordingControls.tsx # Start/stop/pause/mode toggle
│   │       └── CodingSuggestions.tsx # E&M/HCC/CPT code display
│   │
│   └── extension/                  # Chrome browser extension
│       ├── manifest.json           # MV3 manifest
│       ├── background.js           # Service worker
│       ├── content/
│       │   ├── ehr_detector.js     # Detect which EHR is loaded
│       │   ├── field_mapper.js     # Map note sections → EHR fields
│       │   └── injector.js         # Inject note text into EHR forms
│       ├── popup/
│       │   └── popup.tsx           # Extension popup UI
│       └── ehr_configs/            # Per-EHR field mapping configs
│           ├── epic_mychart.json
│           ├── athena.json
│           └── eclinicalworks.json
│
├── data/                           # Reference data + dictionaries
│   ├── medical_wordlist.txt        # 98K OpenMedSpel
│   ├── icd10_codes.csv
│   ├── cpt_codes.csv
│   └── drug_database.csv
│
├── scripts/                        # Operational scripts
│   ├── setup.sh                    # Full stack setup
│   ├── pull_models.sh              # ollama pull all required models
│   ├── seed_templates.py           # Load default templates
│   ├── benchmark_asr.py            # Compare ASR engines on test audio
│   ├── benchmark_llm.py            # Compare LLM note quality
│   └── retrain_postprocessor.sh    # Run post-processor retraining
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── deploy/
    ├── Dockerfile.api              # API server
    ├── Dockerfile.gpu              # GPU services (ASR + LLM)
    ├── docker-compose.yml          # Full local stack
    ├── docker-compose.gpu.yml      # GPU override
    └── k8s/                        # Kubernetes manifests (future)
```

---

## 12. Getting Started (Claude Code Sequence)

```
SESSION 1:  Project scaffolding + state schema + LangGraph skeleton
SESSION 2:  Ollama MCP server + basic note generation (text in → note out)
SESSION 3:  WhisperX MCP server + transcribe node (audio in → transcript out)
SESSION 4:  Post-processor integration (transcript cleanup pipeline)
SESSION 5:  FastAPI backend + WebSocket audio streaming
SESSION 6:  Next.js web app — recording UI + review/edit UI
SESSION 7:  End-to-end integration: capture → transcribe → note → review
SESSION 8:  Provider profiles + template engine
SESSION 9:  Browser extension (Super Fill MVP)
SESSION 10: Offline buffering + sync engine
SESSION 11: Evidence-linked citations (audio indexer + playback)
SESSION 12: Learning service (correction capture + training pair generation)
```
