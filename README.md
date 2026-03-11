# AI Scribe

Fully self-hosted, HIPAA-compliant AI medical scribe. Converts doctor-patient conversations and dictations into structured clinical notes.

## Architecture

- **LangGraph** pipeline: Context → Capture → Transcribe → Note → Review → Delivery
- **MCP tool servers** for plug-and-play engine swapping (ASR, LLM, EHR, audio)
- **Ollama** as default LLM server (Qwen 2.5, Llama, Mistral)
- **WhisperX** as default ASR (faster-whisper + pyannote diarization)
- **12-stage post-processor** with 98K medical dictionary for transcript cleanup
- Zero cloud dependencies. PHI never leaves your infrastructure.

## Quick Start

```bash
# 1. Install Ollama and pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:32b

# 2. Install Python dependencies
pip install -e ".[dev]"

# 3. Run the pipeline on a test file
python -m orchestrator.graph --audio data/dictation/sample_001/audio.mp3
```

## Documentation

- [Architecture](docs/architecture.md) — Full system design
- [CLAUDE.md](CLAUDE.md) — Build instructions for Claude Code

## License

Proprietary. All third-party components are open-source with permissive licenses (MIT, Apache 2.0, CC-BY-4.0).
