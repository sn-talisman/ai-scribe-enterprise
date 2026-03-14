"""
config/paths.py — Centralized, configurable data paths.

All data directory paths are resolved here. Modules import from this file
instead of hardcoding paths. Paths can be overridden via environment variables:

    AI_SCRIBE_ROOT        Base project root (default: auto-detected)
    AI_SCRIBE_DATA_DIR    Patient encounter data (default: {root}/ai-scribe-data)
    AI_SCRIBE_OUTPUT_DIR  Pipeline output (default: {root}/output)
    AI_SCRIBE_CONFIG_DIR  Config files (default: {root}/config)

Example:
    export AI_SCRIBE_DATA_DIR=/mnt/efs/ai-scribe-data
    export AI_SCRIBE_OUTPUT_DIR=/mnt/efs/output
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root: two levels up from config/paths.py → repo root
_DEFAULT_ROOT = Path(__file__).resolve().parent.parent

ROOT = Path(os.environ.get("AI_SCRIBE_ROOT", str(_DEFAULT_ROOT)))
DATA_DIR = Path(os.environ.get("AI_SCRIBE_DATA_DIR", str(ROOT / "ai-scribe-data")))
OUTPUT_DIR = Path(os.environ.get("AI_SCRIBE_OUTPUT_DIR", str(ROOT / "output")))
CONFIG_DIR = Path(os.environ.get("AI_SCRIBE_CONFIG_DIR", str(ROOT / "config")))
PROVIDERS_DIR = CONFIG_DIR / "providers"
