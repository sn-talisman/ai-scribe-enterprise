# CLAUDE.md — AI Scribe Project Instructions

## What This Project Is

AI Scribe is a fully self-hosted, HIPAA-compliant medical documentation system. It converts doctor-patient conversations (ambient mode) and physician dictations (dictation mode) into structured clinical notes (SOAP, H&P, Progress Notes).

Every AI component is pluggable — ASR engines, LLMs, diarization, noise suppression — all behind MCP interfaces, swappable via config, never code changes.

## Architecture (read docs/architecture.md for full detail)

The encounter pipeline is a **LangGraph state graph** with 6 nodes:

```
CONTEXT → CAPTURE → TRANSCRIBE → NOTE → REVIEW → DELIVERY
                                                    ↓
                                              FEEDBACK LOOP
```

Each node has pre-processing → core execution → post-processing steps.
Each node connects to tools via **MCP tool servers**.
Engine selection is governed by **provider profiles** and an **engine registry**.

### Technology Stack (All Self-Hosted, All Open Source)

| Layer | Default | Alternatives |
|-------|---------|-------------|
| ASR (batch) | WhisperX (faster-whisper + pyannote 3.1 + wav2vec2) | NVIDIA Parakeet |
| ASR (streaming) | NVIDIA Nemotron-Speech-Streaming | WhisperX chunked |
| Diarization | pyannote 3.1 (via WhisperX) | NVIDIA Multitalker-Parakeet |
| Noise suppression | DeepFilterNet | RNNoise, passthrough |
| VAD | Silero VAD | WebRTC VAD |
| LLM inference | Ollama (OpenAI-compatible API) | vLLM, SGLang |
| LLM model | Qwen 2.5-32B (Apache 2.0) | Llama 3.1-70B, Mistral |
| Post-processing | 12-stage rule-based pipeline + 98K medical dict | ByT5 ML model (future) |
| Orchestration | LangGraph | — |
| Database | PostgreSQL | — |
| Object storage | MinIO (S3-compatible) | Local filesystem |
| Cache/queue | Valkey (Redis fork, BSD) | Redis |
| Web app | Next.js + React | — |
| Browser extension | Chrome MV3 | — |
| Monitoring | Grafana + Prometheus | — |

### MCP Tool Server Pattern

Every external capability is an MCP server. Nodes never call engines directly.

```python
# Example: LLM MCP server wraps Ollama's OpenAI-compatible API
# Switching to vLLM or Claude = change the URL in config/engines.yaml
# Same interface, same request/response format

class OllamaLLMServer(BaseLLMServer):
    def generate(self, system_prompt, messages, config) -> LLMResponse:
        # POST to http://localhost:11434/v1/chat/completions
        ...
```

All MCP servers implement a base interface defined in `mcp_servers/{type}/base.py`.

### Engine Configuration

```yaml
# config/engines.yaml controls ALL engine selection
# Zero code changes to swap engines

llm:
  default_server: ollama
  servers:
    ollama:
      url: "http://localhost:11434/v1"
      models:
        note_generation: "qwen2.5:32b"
        coding: "qwen2.5:32b"
        patient_summary: "qwen2.5:14b"
        command_parse: "qwen2.5:7b"

asr:
  default_server: whisperx
  servers:
    whisperx:
      model: "large-v3"
      device: "cuda"
      diarization: true
```

## Test Data

The `data/` folder contains real medical audio and transcripts for testing:

```
data/
├── dictation/           # Single-speaker physician dictations
│   ├── sample_001/
│   │   ├── audio.mp3
│   │   ├── transcript_medasr.txt    # MedASR CTC output (garbled)
│   │   ├── transcript_whisper.txt   # Whisper output (cleaner)
│   │   ├── soap_note.txt            # Gold-standard SOAP note
│   │   ├── patient_context.yaml     # Extracted demographics (Session 7)
│   │   ├── generated_note_v1.md     # Session 4 output (basic pipeline)
│   │   ├── generated_note_v2.md     # Session 5 output (templates + specialty)
│   │   ├── generated_note_v3.md     # Session 7 output (full context + demographics)
│   │   ├── comparison_v3.md         # Side-by-side: gold vs generated (per section table)
│   │   └── quality_report.md        # Quality evaluation with scores + fact check
│   └── ...
├── conversation/        # Multi-speaker ambient encounters
│   ├── sample_001/
│   │   ├── audio.mp3
│   │   ├── transcript.txt
│   │   ├── soap_note.txt            # Gold-standard SOAP note
│   │   ├── patient_context.yaml     # Extracted demographics (Session 7)
│   │   ├── generated_note_v1.md
│   │   ├── generated_note_v2.md
│   │   ├── generated_note_v3.md
│   │   ├── comparison_v3.md
│   │   └── quality_report.md
│   └── ...
└── README.md
```

**Output format:** ALL generated notes, transcripts, quality reports, and comparisons are
Markdown (.md) files with proper headers, sections, and tables. This makes them readable,
diffable, and directly comparable with the gold standard documents.

**Version tracking:** Generated outputs are versioned across sessions:
- `v1` = Session 4 (basic end-to-end, no templates)
- `v2` = Session 5 (templates + specialty dictionaries)
- `v3` = Session 7 (full patient context + demographics — should match gold completeness)

Each version should show measurable improvement over the previous.

## Existing Code to Integrate

The `postprocessor/` directory contains our existing ASR post-processing pipeline:

- `medasr_postprocessor.py` — 12-stage rule-based transcript cleanup (1,659 lines, production-tested)
- `medical_wordlist.txt` — 98K OpenMedSpel medical terms dictionary
- `ml/` — ML training pipeline for ByT5-based post-processor (future)

This pipeline runs as a post-processing step in the Transcribe Node. It corrects:
- CTC stutter pairs (90% reduction)
- Character-level stutters (99% reduction)  
- Non-dictionary medical terms (87% reduction)
- MedASR system artifacts ([unintelligible], {format commands}, fillers)

## Project Structure

```
ai-scribe/
├── CLAUDE.md                       # THIS FILE
├── README.md
├── pyproject.toml                  # Python project config (use uv or poetry)
├── docker-compose.yml              # Full local stack
│
├── config/
│   ├── engines.yaml                # Engine configuration (plug-and-play)
│   ├── quality_baseline.yaml       # Best-known quality parameters (Session 6)
│   ├── templates/                  # Note templates by specialty + visit type
│   │   ├── soap_default.yaml
│   │   ├── ortho_first_visit.yaml
│   │   ├── ortho_follow_up.yaml
│   │   ├── gi_first_visit.yaml
│   │   └── ... (auto-generated from gold note analysis)
│   ├── dictionaries/               # Specialty-specific medical vocabularies
│   │   ├── base_medical.txt        # 98K OpenMedSpel (symlinked from postprocessor/)
│   │   ├── orthopedic.txt
│   │   ├── gastroenterology.txt
│   │   ├── cardiology.txt
│   │   ├── neurology.txt
│   │   ├── psychiatry.txt
│   │   ├── pediatrics.txt
│   │   └── custom/                 # Provider-specific custom terms
│   │       └── {provider_id}.txt
│   └── prompts/                    # LLM system prompts
│       ├── note_generation.yaml
│       ├── coding_suggestion.yaml
│       └── patient_summary.yaml
│
├── orchestrator/                   # LangGraph encounter pipeline
│   ├── graph.py                    # Top-level encounter graph
│   ├── state.py                    # EncounterState Pydantic schema
│   ├── nodes/                      # Pipeline stage implementations
│   │   ├── context_node.py
│   │   ├── capture_node.py
│   │   ├── transcribe_node.py
│   │   ├── note_node.py
│   │   ├── review_node.py
│   │   └── delivery_node.py
│   ├── edges/                      # Conditional routing
│   │   ├── asr_router.py
│   │   ├── llm_router.py
│   │   ├── confidence_router.py
│   │   └── mode_router.py
│   └── subgraphs/
│       ├── postprocessor_graph.py  # Rules vs ML routing
│       └── note_parallel_graph.py  # Parallel note+coding+summary
│
├── mcp_servers/                    # Plug-and-play tool servers
│   ├── registry.py                 # Engine registry + health checks
│   ├── asr/
│   │   ├── base.py                 # ASREngine interface
│   │   ├── whisperx_server.py      # DEFAULT
│   │   ├── nemo_streaming_server.py
│   │   ├── assemblyai_server.py    # Cloud option
│   │   └── deepgram_server.py      # Cloud option
│   ├── llm/
│   │   ├── base.py                 # LLMEngine interface
│   │   ├── ollama_server.py        # DEFAULT
│   │   ├── vllm_server.py
│   │   └── claude_server.py        # Cloud option
│   ├── ehr/
│   │   ├── base.py                 # EHRAdapter interface
│   │   ├── stub_server.py          # DEFAULT — reads from local YAML files
│   │   ├── fhir_server.py          # Future: live FHIR R4 integration
│   │   ├── extension_server.py     # Future: browser extension bridge
│   │   └── manual_server.py        # Future: manual entry
│   ├── audio/
│   │   ├── deepfilternet_server.py
│   │   ├── silero_vad_server.py
│   │   └── ffmpeg_server.py
│   └── data/
│       ├── medical_dict_server.py  # Base + specialty dictionary loader
│       ├── template_server.py
│       └── icd10_server.py
│
├── postprocessor/                  # ASR post-processing (EXISTING CODE)
│   ├── medasr_postprocessor.py     # 12-stage rule-based pipeline
│   ├── medical_wordlist.txt        # 98K OpenMedSpel dictionary
│   └── ml/                         # ML post-processor (future)
│       ├── generate_training_data.py
│       ├── train_model.py
│       ├── inference.py
│       └── evaluate.py
│
├── learning/                       # Continuous improvement
│   ├── correction_capture.py
│   ├── style_model.py
│   ├── quality_monitor.py
│   └── ab_test.py
│
├── quality/                        # Quality evaluation framework (Session 6)
│   ├── __init__.py
│   ├── evaluator.py                # Central quality scoring (LLM-as-judge + fact extraction)
│   ├── report.py                   # Per-encounter and aggregate quality reports (.md)
│   ├── optimizer.py                # Parameter optimization loop
│   ├── dimensions.py               # Scoring rubric definitions
│   ├── fact_extractor.py           # Extract medications, diagnoses, findings from notes
│   ├── experiments.jsonl            # Log of all optimization experiments
│   └── regression.py               # Quality regression testing
│
├── output/                         # Markdown output writer + batch reports
│   ├── __init__.py
│   ├── markdown_writer.py          # Renders clinical notes as formatted .md files
│   ├── comparison_writer.py        # Renders side-by-side gold vs generated .md files
│   └── batch_report_v{N}.md        # Aggregate quality reports per pipeline version
│
├── trigger/                        # Production ingestion triggers (Session 10)
│   ├── s3_handler.py               # S3 upload → pipeline invocation
│   └── eventbridge_config.json     # EventBridge rule definition
│
├── api/                            # FastAPI backend (Session 12)
│   ├── main.py
│   ├── routes/
│   │   ├── encounters.py
│   │   ├── providers.py
│   │   ├── audio.py
│   │   └── notes.py
│   └── ws/
│       ├── audio_stream.py
│       └── session_events.py
│
├── client/                         # Frontend (Sessions 13-14)
│   ├── web/                        # Next.js web application
│   └── extension/                  # Chrome browser extension
│
├── data/                           # Test data (gitignored, local only)
│   ├── dictation/
│   │   └── sample_001/
│   │       ├── audio.mp3
│   │       ├── soap_note.txt               # Gold standard
│   │       ├── patient_context.yaml        # Extracted demographics (Session 7)
│   │       ├── generated_note_v1.md        # Session 4 output
│   │       ├── generated_note_v2.md        # Session 5 output (templates)
│   │       ├── generated_note_v3.md        # Session 7 output (full context)
│   │       ├── comparison_v3.md            # Side-by-side vs gold
│   │       └── quality_report.md           # Quality evaluation
│   ├── conversation/
│   │   └── (same structure as dictation/)
│   └── README.md
│
├── scripts/
│   ├── setup.sh                    # Project setup
│   ├── pull_models.sh              # ollama pull required models
│   ├── benchmark_asr.py            # ASR engine comparison
│   ├── analyze_gold_notes.py       # Analyze gold notes → generate templates (Session 5)
│   ├── build_specialty_dicts.py    # Generate specialty dictionaries (Session 5)
│   ├── extract_patient_context.py  # Extract demographics from gold notes (Session 7)
│   ├── run_quality_sweep.py        # Run pipeline + evaluate all samples (Session 6)
│   └── compare_versions.py         # Side-by-side output comparison (Session 6)
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── deploy/
│   ├── Dockerfile.api
│   ├── Dockerfile.gpu
│   └── docker-compose.yml
│
└── docs/
    └── architecture.md             # Full system architecture
```

## Build Sequence

Follow this order. Each session builds on the previous.

**Sessions 1-8 focus on pipeline quality — getting the best possible clinical note from audio.**
**Sessions 9+ add infrastructure, UI, and integration layers on top of the proven pipeline.**

### Output Format Convention

ALL generated outputs are **Markdown (.md) files** with proper headers, sections, and formatting so they are human-readable and diff-comparable:

```markdown
# Clinical Note — [Patient Name / ID]
**Date:** 2024-03-07 | **Provider:** Dr. Smith | **Visit Type:** Follow-up
**Specialty:** Orthopedic | **Template:** ortho_follow_up

---

## Chief Complaint
Patient presents for follow-up evaluation of cervical spine injury...

## History of Present Illness
...

## Assessment
1. Acute cervical strain, improving
2. Right wrist sprain, stable
...

## Plan
1. Continue physical therapy 2x/week
2. Naproxen 500mg BID as needed
...
```

**Comparison documents** are also Markdown with side-by-side sections:

```markdown
# Quality Comparison — sample_001
**Version:** v3 (Session 7) vs Gold Standard

---

## Chief Complaint
| Gold | Generated | Score |
|------|-----------|-------|
| Patient presents for initial evaluation of injuries sustained in MVA on 2/19... | Patient presents for initial evaluation of motor vehicle accident injuries... | 4.5/5 |

## History of Present Illness
| Gold | Generated | Score |
|------|-----------|-------|
| (gold text) | (generated text) | 4.2/5 |

...

## Summary
| Dimension | Score |
|-----------|-------|
| Medical Accuracy | 4.5 |
| Completeness | 4.0 |
| Hallucination-Free | 5.0 |
| **Overall** | **4.3** |
```

### Session 1: Project Scaffolding + State Schema + LangGraph Skeleton
- Initialize Python project with pyproject.toml (use Python 3.11+)
- Define EncounterState Pydantic schema in `orchestrator/state.py`
- Create the top-level LangGraph in `orchestrator/graph.py` with stub nodes
- Create base interfaces: `mcp_servers/asr/base.py`, `mcp_servers/llm/base.py`, `mcp_servers/ehr/base.py`
- Create `config/engines.yaml` with default configuration
- Wire up basic test: state flows through all 6 stub nodes
- Implement Markdown output writer in `output/markdown_writer.py` — all generated notes are `.md` files

### Session 2: Ollama LLM Server + Note Generation
- Implement `mcp_servers/llm/ollama_server.py` (wraps Ollama OpenAI-compat API)
- Implement `mcp_servers/llm/base.py` LLMEngine interface
- Create prompt templates in `config/prompts/note_generation.yaml`
- Implement `orchestrator/nodes/note_node.py` (prompt assembly → LLM call → parse)
- Output format: generated notes written as `.md` files with proper clinical headers
- Test: feed a transcript string → get a formatted Markdown SOAP note back
- Use test data from `data/dictation/` transcripts as input

### Session 3: WhisperX ASR Server + Transcribe Node
- Implement `mcp_servers/asr/whisperx_server.py`
- Implement `mcp_servers/asr/base.py` ASREngine interface
- Implement `orchestrator/nodes/transcribe_node.py`
- Integrate post-processor: `postprocessor/medasr_postprocessor.py`
- Output format: cleaned transcripts written as `.md` with speaker labels and timestamps
- Test: feed audio file → get cleaned, diarized transcript `.md`
- Use test audio from `data/dictation/` and `data/conversation/`

### Session 4: End-to-End Pipeline
- Wire Transcribe → Note nodes together in the graph
- Implement ASR Router (conditional edge) with single engine initially
- Implement LLM Router with single engine
- Test: audio file → transcript → SOAP note `.md` (full pipeline)
- Generate notes for ALL samples in `data/dictation/` and `data/conversation/`
- Save as `generated_note_v1.md` alongside each sample
- Generate `comparison_v1.md` for each sample showing generated vs gold side-by-side
- Save aggregate report as `output/batch_report_v1.md`

### Session 5: Templates & Specialization
This session makes the note generation specialty-aware and template-driven.

**a. Generic Template Engine**
- Implement template system in `config/templates/` that supports arbitrary note formats
- Each template is a YAML file defining: sections (ordered), required fields, section prompts, formatting rules, and demographic/patient header fields
- Template types include but are not limited to: first_visit, follow_up, procedure_note, consultation, discharge_summary
- The template engine is GENERIC — any new YAML template dropped into `config/templates/` is automatically available
- Templates are selected per-encounter based on: visit type + provider specialty + provider preference
- Implement in `mcp_servers/data/template_server.py` and wire into Note Node's prompt assembly
- Template structure:
  ```yaml
  # config/templates/ortho_first_visit.yaml
  name: "Orthopedic First Visit"
  specialty: orthopedic
  visit_type: first_visit
  header_fields:
    - patient_name
    - date_of_service
    - date_of_birth
    - provider_name
    - referring_provider
    - location
  sections:
    - id: chief_complaint
      label: "Chief Complaint"
      required: true
      prompt_hint: "One-sentence reason for visit"
    - id: hpi
      label: "History of Present Illness"
      required: true
      prompt_hint: "Detailed narrative including: mechanism of injury, date of onset, progression, aggravating/alleviating factors, prior treatment"
    - id: past_medical_history
      label: "Past Medical History"
      required: true
    - id: past_surgical_history
      label: "Past Surgical History"
      required: true
    - id: medications
      label: "Current Medications"
      required: true
    - id: allergies
      label: "Allergies"
      required: true
    - id: social_history
      label: "Social History"
      required: false
    - id: review_of_systems
      label: "Review of Systems"
      required: true
    - id: physical_exam
      label: "Physical Examination"
      required: true
      prompt_hint: "Include inspection, palpation, ROM (in degrees), strength, special tests, neurovascular status"
    - id: imaging
      label: "Imaging / Diagnostics"
      required: false
    - id: assessment
      label: "Assessment"
      required: true
      prompt_hint: "Numbered list of diagnoses with ICD-10 codes if identifiable"
    - id: plan
      label: "Plan"
      required: true
      prompt_hint: "Numbered plan items corresponding to each assessment item"
  formatting:
    voice: active
    abbreviations: spell_out
    measurements: include_units
  ```

**b. Gold Document Analysis + Template Creation**
- Write `scripts/analyze_gold_notes.py` that reads ALL gold-standard notes from both `data/dictation/` and `data/conversation/`
- Analyze the gold documents using the LLM (via Ollama) to extract:
  - Common section structure (which sections appear, in what order)
  - Section-level patterns (how HPI is written, what Assessment typically includes)
  - Style patterns (voice, tense, abbreviation usage, level of detail)
  - Differences between first visit vs follow-up patterns
  - Differences between dictation-sourced vs conversation-sourced notes
  - Patient/demographic fields present in headers
- Generate template YAML files from this analysis — one per detected note type
- Generate example style directives from the analysis
- Run the full pipeline on ALL samples using the generated templates
- Save as `generated_note_v2.md` for each sample
- Generate `comparison_v2.md` with side-by-side Markdown tables (gold vs generated per section)
- Save aggregate report as `output/batch_report_v2.md`

**c. Specialty Dictionaries**
- Create `config/dictionaries/` folder for specialty-specific medical vocabularies
- Implement specialty dictionary loader in `mcp_servers/data/medical_dict_server.py`
- Structure:
  ```
  config/dictionaries/
  ├── base_medical.txt            # 98K OpenMedSpel (already have this)
  ├── orthopedic.txt              # ROM terms, joint anatomy, implants, procedures
  ├── gastroenterology.txt        # Endoscopy, hepatology, motility terms
  ├── cardiology.txt              # Arrhythmias, catheterization, cardiac meds
  ├── neurology.txt               # Cranial nerves, EEG, stroke scales
  ├── psychiatry.txt              # DSM terms, mental status exam vocabulary
  ├── pediatrics.txt              # Growth/development, immunizations
  └── custom/                     # Provider-specific terms
      └── {provider_id}.txt
  ```
- Build specialty dictionaries by:
  1. Mining gold SOAP notes for specialty-specific terms not in base dictionary
  2. Supplementing from public medical terminology databases
  3. Using the LLM to generate comprehensive term lists per specialty
- Wire specialty dictionaries into:
  - Post-processor (Stage 10-11: dictionary matching + medical spellcheck)
  - Note Node (LLM prompt: specialty vocabulary context)
  - ASR (WhisperX initial_prompt / hotwords)

**d. Full Pipeline Execution with Specialty Context**
- Run pipeline on ALL samples with specialty context loaded
- All outputs as properly formatted Markdown clinical notes
- Save all outputs with version tracking for comparison across sessions

### Session 6: Output Quality Measurement & Optimization
This session builds the quality evaluation framework and iteratively tunes the pipeline.

**a. Quality Evaluation Framework**
- Build `quality/evaluator.py` — central quality measurement system
- All quality reports generated as **Markdown files**
- Implement multiple evaluation approaches (word-matching does NOT work for clinical notes):

  **Semantic Similarity (primary metric):**
  - Use the local LLM as a judge: score (gold_note, generated_note) pairs
  - Scoring rubric (each 1-5): Medical accuracy, Completeness, No hallucination, Structure compliance, Clinical language, Readability
  - Overall score = weighted combination

  **Section-Level Evaluation:**
  - Compare section-by-section with Markdown table output
  - For each section: semantic similarity score via LLM judge
  - Identify: missing sections, extra sections, wrong content

  **Factual Extraction Comparison:**
  - Extract key facts from both notes using LLM: medications (name, dose, frequency), diagnoses, physical exam findings, plan items
  - Compute precision/recall on extracted facts
  - Catches: "note reads well but missed a medication"

  **Transcript Coverage:**
  - What % of clinically relevant transcript content is in the note?
  - Flag important transcript segments missing from note

- Quality report per encounter saved as `quality_report.md`:
  ```markdown
  # Quality Report — sample_001
  **Pipeline Version:** v2 | **Date:** 2024-03-08

  ## Overall Score: 4.2 / 5.0

  ## Dimension Scores
  | Dimension | Score | Notes |
  |-----------|-------|-------|
  | Medical accuracy | 4.5 | |
  | Completeness | 3.8 | ⚠ Missing: left knee ROM measurements |
  | No hallucination | 5.0 | |
  | Structure compliance | 4.0 | |
  | Clinical language | 4.5 | |
  | Readability | 4.0 | |

  ## Fact Check
  | Category | Found | Total | Missed |
  |----------|-------|-------|--------|
  | Medications | 5 | 5 | — |
  | Diagnoses | 3 | 3 | — |
  | Exam findings | 8 | 10 | left knee crepitus, patellar grind |
  | Plan items | 4 | 4 | — |

  ## Section Comparison
  (side-by-side Markdown table of gold vs generated per section)
  ```

**b. Parameter Optimization Loop**
- Build `quality/optimizer.py` — systematically tunes all pipeline parameters
- Parameters: post-processor thresholds, LLM temperature/top_p, prompt variations, context budget, few-shot examples, ASR beam_size, VAD sensitivity
- Strategy: run full pipeline → identify weakest dimensions → LLM analyzes failures → suggest parameter changes → re-run → compare → accept/revert
- All experiments logged in `quality/experiments.jsonl`
- NOT grid search — use LLM to reason about failure patterns

**c. Batch Execution & Reporting**
- `scripts/run_quality_sweep.py`: runs pipeline on all samples, evaluates, produces:
  - Per-sample: `quality_report.md` + `comparison_v{N}.md`
  - Aggregate: `output/batch_report_v{N}.md` with summary statistics
  - `output/worst_samples.md` identifying samples needing most improvement
- `scripts/compare_versions.py`: side-by-side across versions as Markdown

**d. Quality Regression Prevention**
- Save best parameters as `config/quality_baseline.yaml`
- `tests/quality/test_regression.py`: assert scores >= baseline before code changes

### Session 7: EHR Context Integration (Stubbed)
This session adds patient demographics and clinical context into the pipeline so generated notes include ALL information present in the gold documents — not just what's in the audio transcript.

**a. Patient Context Extraction from Gold Documents**
- Write `scripts/extract_patient_context.py` that analyzes all gold-standard notes to extract structured patient/demographic data:
  - Patient name (or identifier)
  - Date of birth / age
  - Sex / gender
  - Date of service
  - Date of injury / onset (if applicable)
  - Provider name and credentials
  - Referring provider (if applicable)
  - Clinic / facility name and location
  - Insurance / claim information (if present)
  - Visit type (initial evaluation, follow-up, re-evaluation)
  - Any other header/demographic fields present in gold notes
- Use the LLM to extract this structured data from each gold note
- Save extracted context as `patient_context.yaml` alongside each sample:
  ```yaml
  # data/dictation/sample_001/patient_context.yaml
  patient:
    name: "Jane Doe"
    date_of_birth: "1985-06-15"
    age: 38
    sex: "Female"
    mrn: "0219-370"
  encounter:
    date_of_service: "2024-03-07"
    visit_type: "initial_evaluation"
    date_of_injury: "2024-02-19"
    mechanism_of_injury: "Motor vehicle accident"
  provider:
    name: "Dr. Smith"
    credentials: "MD"
    specialty: "Orthopedic"
    npi: ""
  facility:
    name: "Regional Medical Center"
    location: ""
  referring_provider:
    name: ""
  insurance:
    carrier: ""
    claim_number: ""
  ```

**b. Context Node Implementation**
- Implement `orchestrator/nodes/context_node.py` fully
- For now, the EHR adapter is stubbed: reads patient context from `patient_context.yaml` files
- The stub EHR adapter (`mcp_servers/ehr/stub_server.py`) implements the full EHR interface but reads from local YAML/JSON files instead of a live EHR
- Context is loaded into EncounterState.context_packet before the pipeline runs
- This context flows through to the Note Node's prompt assembly

**c. Template Updates for Demographics**
- Update all templates to include demographic header fields
- The Note Node prompt assembler now includes patient context:
  ```
  PATIENT CONTEXT:
  Name: Jane Doe | DOB: 06/15/1985 | Sex: Female
  Date of Service: 03/07/2024 | Visit Type: Initial Evaluation
  Date of Injury: 02/19/2024 | Mechanism: Motor vehicle accident
  Provider: Dr. Smith, MD | Facility: Regional Medical Center

  TRANSCRIPT:
  (cleaned transcript from Transcribe Node)

  Generate a clinical note using the template below...
  ```
- Generated Markdown notes now include a complete header:
  ```markdown
  # Clinical Note
  **Patient:** Jane Doe | **DOB:** 06/15/1985 | **Sex:** Female
  **Date of Service:** 03/07/2024 | **Visit Type:** Initial Evaluation
  **Date of Injury:** 02/19/2024 | **Mechanism:** MVA
  **Provider:** Dr. Smith, MD | **Specialty:** Orthopedic
  **Facility:** Regional Medical Center

  ---

  ## Chief Complaint
  ...
  ```

**d. Full Pipeline Execution with Complete Context**
- Run the complete pipeline on ALL samples with:
  - Patient context loaded from extracted YAML
  - Specialty dictionary loaded based on provider specialty
  - Appropriate template selected based on visit type + specialty
- The goal: generated notes should include ALL details present in the gold documents
  - Demographics in header ✓
  - Dates, provider info, facility ✓
  - All clinical sections with content from both transcript AND context ✓
- Save as `generated_note_v3.md` for each sample
- Generate `comparison_v3.md` with side-by-side comparison against gold
- Quality evaluation: run full quality sweep → `output/batch_report_v3.md`
- This version should score significantly higher on completeness and structure compliance since it now has the same information the gold notes had

**e. Stub EHR Interface for Future Integration**
- `mcp_servers/ehr/stub_server.py` implements the full EHRAdapter interface:
  ```python
  class StubEHRServer(BaseEHRServer):
      """Reads patient context from local YAML files.
      Replace with FHIRServer, HL7Server, or ExtensionServer later.
      Same interface — zero code changes in the pipeline."""

      async def get_patient(self, identifier) -> PatientDemographics
      async def get_problem_list(self, patient_id) -> list[Problem]
      async def get_medications(self, patient_id) -> list[Medication]
      async def get_allergies(self, patient_id) -> list[Allergy]
      async def get_recent_labs(self, patient_id) -> list[LabResult]
      async def get_last_visit_note(self, patient_id) -> ClinicalNote
      async def push_note(self, patient_id, note) -> PushResult
  ```
- When real EHR integration is built (later sessions), only the MCP server implementation changes — the pipeline code, prompts, and templates are untouched

### Session 8: Provider Profiles + Provider-Specific Tuning
- Implement provider profile CRUD (PostgreSQL or local YAML for now)
- Provider-specific template selection (specialty + visit type → template)
- Provider-specific dictionary loading (specialty + custom vocabulary)
- Style directive injection into LLM prompts (from provider profile)
- Custom vocabulary per provider → ASR keyterm boosting
- Per-provider quality tracking: store quality scores per provider, track improvement

### Session 9: FastAPI Backend + Web UI Viewer
This session wires the pipeline to a web interface so all results can be browsed, reviewed, and triggered from a browser. The UI is a **viewer and dashboard only** — audio upload is supported but live recording is deferred to a later session.

**Design System — Talisman Solutions Style**
- Color palette: primary green `#00B27A`, accent purple/indigo `#6366F1`, neutral dark sidebar `#1E1B4B`
- Card-based KPI tiles, clean sidebar navigation, combo bar+line charts for quality trends
- Typography: Inter (sans-serif), 14px base, generous whitespace
- All charts: Recharts (React); all tables sortable; dark sidebar + light main panel

**a. FastAPI Backend (`api/`)**
- `api/main.py` — FastAPI app with CORS, structured logging, startup/shutdown lifecycle
- Encounter lifecycle routes (`api/routes/encounters.py`):
  - `POST /encounters` — create encounter (provider_id, patient_id, visit_type, mode)
  - `POST /encounters/{id}/upload` — upload audio file (multipart); triggers pipeline async
  - `GET  /encounters/{id}` — poll status (pending / processing / complete / error)
  - `GET  /encounters/{id}/transcript` — return cleaned transcript (Markdown)
  - `GET  /encounters/{id}/note` — return generated clinical note (Markdown)
  - `GET  /encounters/{id}/comparison` — return gold vs generated comparison (Markdown)
  - `GET  /encounters/{id}/quality` — return quality report JSON + Markdown
- Provider routes (`api/routes/providers.py`):
  - `GET  /providers` — list all provider profiles
  - `GET  /providers/{id}` — get profile + quality history
  - `GET  /providers/{id}/quality-trend` — quality history as chart-ready JSON
- Quality routes (`api/routes/quality.py`):
  - `GET  /quality/aggregate` — overall stats across all samples + versions
  - `GET  /quality/samples` — per-sample scores (filterable by version, provider, visit_type)
  - `GET  /quality/dimensions` — dimension breakdown averages
- WebSocket (`api/ws/session_events.py`): `WS /ws/encounters/{id}` — real-time pipeline progress events (stage name, % complete, log lines)
- Background task runner: upload handler enqueues pipeline run via `asyncio.create_task`; sends WS events at each LangGraph node transition
- Data source: reads existing `output/` directory structure + provider YAML files; no database required for this session

**b. Next.js Web App (`client/web/`)**
- `npx create-next-app@latest` with TypeScript + Tailwind CSS
- Package additions: `recharts`, `react-markdown`, `react-syntax-highlighter`, `@radix-ui/react-tabs`, `lucide-react`
- Sidebar navigation: Dashboard | Samples | Providers | Upload

**Dashboard (`/`)**
- KPI cards (4 across): Total Samples, Average Quality Score, Best Sample, Latest Version
- Quality trend chart: line chart of avg score per version (v1 → v2 → v3 → v4)
- Dimension radar chart: accuracy / completeness / no-hallucination / structure / language / readability
- Recent encounters table: sample_id, visit_type, version, score, date

**Sample Browser (`/samples`)**
- Filterable table: version, visit_type (dictation/conversation), score range
- Row click → Sample Detail page

**Sample Detail (`/samples/[id]`)**
- Tabs: Transcript | Clinical Note | Comparison | Quality Report
- Transcript tab: Markdown renderer with speaker labels (DOCTOR / PATIENT) highlighted in green/indigo
- Clinical Note tab: rendered Markdown with section headers styled as cards
- Comparison tab: two-column table (Gold | Generated) with per-section score badge
- Quality Report tab: dimension score bar chart + fact-check table
- "Re-run Pipeline" button → `POST /encounters` then polls WS for progress

**Upload (`/upload`)**
- Drag-and-drop audio file zone (MP3, WAV, M4A)
- Provider selector (dropdown from `/providers`)
- Visit type selector (initial_evaluation / follow_up)
- Submit → `POST /encounters` + `POST /encounters/{id}/upload` → redirects to Sample Detail with live WS progress bar

**Providers (`/providers`)**
- Provider cards: name, specialty, latest quality score badge
- Provider detail: style directives list, custom vocabulary chips, quality history line chart

**c. Integration**
- API base URL configured via `NEXT_PUBLIC_API_URL` env var (default `http://localhost:8000`)
- All Markdown content rendered with `react-markdown` + `remark-gfm` for tables
- WebSocket connection managed with `useWebSocket` custom hook; progress shown as animated step indicator

**d. Dev Setup**
- `api/`: `uvicorn api.main:app --reload --port 8000`
- `client/web/`: `npm run dev` (port 3000)
- Add both to `docker-compose.yml` for one-command startup

### Session 10: ASR Quality Improvement — Physician-Specific Fine-Tuning
This session improves transcription accuracy for individual physicians by fine-tuning Whisper on provider-specific audio and notes, capturing idiosyncratic pronunciation, accent, vocabulary, and dictation style.

**a. Data Preparation Pipeline (`scripts/prepare_asr_training_data.py`)**
- For each sample pair (audio + gold note / transcript):
  - Align gold transcript words to audio using WhisperX forced alignment (wav2vec2)
  - Produce word-level `(start_time, end_time, word)` segments
  - Segment audio into 10–30 second chunks with corresponding text
  - Output: HuggingFace `datasets`-compatible `DatasetDict` with `{audio, sentence}` fields
- Filtering: skip chunks with alignment confidence < 0.6 or duration > 30s
- Augmentation: speed perturbation ±10%, additive noise at SNR 15–25 dB (using `audiomentations`)
- Save to `data/asr_training/{provider_id}/` in HuggingFace Arrow format

**b. LoRA Adapter Fine-Tuning (`scripts/finetune_whisper_lora.py`)**
- Base model: `openai/whisper-large-v3` (same as production)
- Method: LoRA via `peft` library — fine-tune only attention + MLP projection layers
  - `r=8`, `lora_alpha=32`, `target_modules=["q_proj","v_proj"]`, `lora_dropout=0.05`
- Training: HuggingFace `Seq2SeqTrainer`
  - `per_device_train_batch_size=4`, `gradient_accumulation_steps=4`, `fp16=True`
  - `learning_rate=1e-4`, `warmup_steps=50`, cosine LR schedule
  - `max_steps=200` (sufficient for ~21 samples with augmentation = ~1,000 chunks)
  - Eval every 50 steps on held-out 10% split; early stop if WER stops improving
- Saves adapter weights to `models/whisper_lora/{provider_id}/` (< 50 MB per provider)
- Full model NOT saved — only LoRA delta weights; base model shared across all providers

**c. Provider-Specific ASR Server (`mcp_servers/asr/whisperx_lora_server.py`)**
- Extends `WhisperXServer`; on initialization loads LoRA adapter via `peft.PeftModel.from_pretrained`
- Engine registry detects if `models/whisper_lora/{provider_id}/` exists → uses LoRA server
- Falls back to base WhisperX server if no adapter exists
- Zero pipeline code changes — same `ASREngine` interface

**d. Evaluation & Comparison (`scripts/eval_asr_quality.py`)**
- Metric: Word Error Rate (WER) and Character Error Rate (CER) on held-out audio
- Compare: base Whisper vs LoRA-fine-tuned on same audio
- Output: `output/asr_eval_{provider_id}.md` — WER/CER table, worst-error examples, medical term accuracy breakdown
- Medical term accuracy: compute separately for terms in provider's custom_vocabulary + specialty dict

**e. Hotword / Keyword Boosting (lighter-weight alternative)**
- For providers where < 5 minutes of audio is available (insufficient for fine-tuning):
  - Use WhisperX `initial_prompt` with 200-word provider-specific vocabulary
  - Use `initial_prompt` to prime the model with the provider's name, clinic, common phrases
  - No training required; immediate improvement for rare medical terms
- `mcp_servers/asr/whisperx_server.py`: `_build_initial_prompt(provider_profile)` constructs the prompt string from `provider.custom_vocabulary + specialty_hotwords[:50]`

**f. Continuous Improvement Hook**
- After each completed encounter, if provider has manually corrected the transcript:
  - New audio + corrected text is added to the training dataset
  - Re-fine-tuning triggered automatically when `new_samples >= 5` (configurable)
  - New LoRA adapter replaces old one; quality metrics compared before activation

### Session 11: Learning Loop + Correction Capture
- Capture provider corrections (diff: AI output vs provider-edited)
- Classify corrections (ASR_ERROR, STYLE, CONTENT, CODING, TEMPLATE)
- Generate training pairs for post-processor ML model
- Update provider style model from edit patterns
- Feed quality evaluator with real correction data
- Trigger ASR re-fine-tuning when enough new corrected transcripts accumulate (see Session 10f)

### Session 12: S3 Trigger Pipeline (Production Ingestion)
- Implement S3 upload watcher: audio files uploaded to designated S3 bucket trigger pipeline
- EventBridge rule: S3 PutObject → invoke pipeline Lambda/container
- Pipeline reads audio from S3, processes through full graph, writes output `.md` back to S3
- Folder structure in S3 mirrors local data structure:
  ```
  s3://ai-scribe-encounters/
  ├── incoming/                  # Drop audio files here → triggers pipeline
  │   └── {encounter_id}.mp3
  ├── context/                   # Patient context YAML (uploaded with audio or pre-populated)
  │   └── {encounter_id}.yaml
  ├── output/                    # Pipeline writes results here
  │   ├── {encounter_id}/
  │   │   ├── transcript.md
  │   │   ├── clinical_note.md
  │   │   ├── quality_report.md
  │   │   └── metadata.json
  └── archive/                   # Completed encounters moved here
  ```
- Implement `trigger/s3_handler.py` — the entry point invoked by EventBridge
- All output files are Markdown, consistent with local pipeline output format

### Session 13: Evidence-Linked Citations + Audio Recording UI
- Audio indexer: word-level timestamp mapping for citation links
- Citation metadata embedded in note Markdown (link note sentences → audio timestamps)
- Add live audio recording to web UI (Session 9 deferred this): WebRTC capture → stream to backend → live transcription via NeMo streaming ASR
- Offline audio buffering strategy for client-side capture (IndexedDB ring buffer)

### Session 14: Browser Extension (Super Fill MVP)
- Chrome MV3 extension scaffold
- EHR detection, field mapping, note injection

### Sessions 15+: Advanced features (coding suggestions, patient summaries, voice commands, mobile app)

## Coding Standards

- **Python**: 3.11+, type hints everywhere, Pydantic for data models
- **Async**: Use async/await for all I/O (API calls, file operations)
- **Error handling**: Every MCP server call wrapped in try/except with fallback logic
- **Configuration**: All engine/model selection via `config/engines.yaml`, never hardcoded
- **Testing**: pytest, test each MCP server independently, test each node independently
- **Logging**: structured logging (structlog), every pipeline step logged with encounter_id
- **Secrets**: environment variables only, never in config files
- **Output format**: ALL generated notes, transcripts, quality reports, and comparisons as Markdown (.md) files with proper headers, sections, and tables

## Important Context

- All audio test data contains PHI — never commit to git, never send to external APIs
- The post-processor in `postprocessor/` is production-tested on 10 real transcripts
- The 98K medical wordlist is GPL-licensed — include attribution
- pyannote requires a HuggingFace token (free) for the diarization model
- Ollama must be installed and running locally before testing LLM nodes
- For GPU nodes (WhisperX, NeMo), CUDA toolkit must be installed
- Gold-standard notes in `data/` are the quality benchmark — every generated note is compared against them
- Generated output versions are tracked: v1 (Session 4), v2 (Session 5), v3 (Session 7), v4 (Session 8) — each should show measurable improvement
