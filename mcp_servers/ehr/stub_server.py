"""
Stub EHR Server — reads patient context from local YAML files.

Implements the full EHRAdapter interface but reads from patient_context.yaml
files instead of a live EHR system.  When real EHR integration is built,
only this file is replaced — the pipeline code is untouched.

Usage:
    server = StubEHRServer.from_config({"type": "stub"})
    patient = await server.get_patient(PatientIdentifier(mrn="1.226680.0"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from mcp_servers.ehr.base import (
    EHRAdapter,
    EHRAllergy,
    EHRLabResult,
    EHRMedication,
    EHRNote,
    EHRPatient,
    EHRProblem,
    NavigationResult,
    PatientIdentifier,
    PushResult,
)

log = logging.getLogger(__name__)


class StubEHRServer(EHRAdapter):
    """
    Reads patient context from local YAML files.

    The context_path can be set per-encounter via set_context_path()
    before calling any read methods.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._context_path: Optional[Path] = None
        self._cache: dict[str, dict] = {}

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "StubEHRServer":
        return cls(data_dir=cfg.get("data_dir", "data"))

    def set_context_path(self, path: str | Path) -> None:
        """Set the patient_context.yaml path for the current encounter."""
        self._context_path = Path(path)
        self._cache.clear()

    def _load_context(self) -> dict:
        """Load and cache the current context YAML."""
        if self._context_path is None:
            return {}
        key = str(self._context_path)
        if key not in self._cache:
            if self._context_path.exists():
                with open(self._context_path) as f:
                    self._cache[key] = yaml.safe_load(f) or {}
                log.debug(f"stub_ehr: loaded context from {self._context_path}")
            else:
                log.warning(f"stub_ehr: context file not found: {self._context_path}")
                self._cache[key] = {}
        return self._cache[key]

    # ── READ ─────────────────────────────────────────────────────────────

    async def get_patient(self, identifier: PatientIdentifier) -> EHRPatient:
        ctx = self._load_context()
        patient = ctx.get("patient", {})
        name = patient.get("name", "")
        parts = name.split(maxsplit=1) if name else ["", ""]
        given = parts[0] if len(parts) > 0 else ""
        family = parts[1] if len(parts) > 1 else ""
        return EHRPatient(
            id=patient.get("mrn", identifier.mrn or "unknown"),
            given_name=given or None,
            family_name=family or None,
            dob=patient.get("date_of_birth"),
            sex=patient.get("sex"),
            mrn=patient.get("mrn"),
        )

    async def get_problem_list(self, patient_id: str) -> list[EHRProblem]:
        # Stub: no problem list in YAML context files
        return []

    async def get_medications(self, patient_id: str) -> list[EHRMedication]:
        return []

    async def get_allergies(self, patient_id: str) -> list[EHRAllergy]:
        return []

    async def get_recent_labs(self, patient_id: str, days: int = 90) -> list[EHRLabResult]:
        return []

    async def get_last_visit_note(self, patient_id: str) -> Optional[EHRNote]:
        return None

    # ── Context accessors (stub-specific) ────────────────────────────────

    def get_encounter_context(self) -> dict:
        """Return the encounter block from patient_context.yaml."""
        return self._load_context().get("encounter", {})

    def get_provider_context(self) -> dict:
        """Return the provider block from patient_context.yaml."""
        return self._load_context().get("provider", {})

    def get_facility_context(self) -> dict:
        """Return the facility block from patient_context.yaml."""
        return self._load_context().get("facility", {})

    # ── WRITE ────────────────────────────────────────────────────────────

    async def push_note(
        self,
        patient_id: str,
        note: EHRNote,
        encounter_id: Optional[str] = None,
    ) -> PushResult:
        log.info(f"stub_ehr: push_note called (stub — no-op) for patient {patient_id}")
        return PushResult(success=True, method="stub")

    # ── NAVIGATE ─────────────────────────────────────────────────────────

    async def navigate(self, command: str) -> NavigationResult:
        return NavigationResult(
            success=False,
            action=command,
            error="Navigation not supported by stub adapter.",
        )

    # ── Health ───────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "stub"
