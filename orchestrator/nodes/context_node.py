"""
CONTEXT NODE — Pre-encounter context assembly.

Real implementation (Session 7):
  PRE:  validate_patient_id → check_ehr_connectivity → load_provider_profile → dedup_session
  CORE: fetch_ehr_data (via MCP EHR tool server)
  POST: check_completeness → optimize_context_size → minimize_phi → snapshot_context

Session 1: Stub — marks status and records node completion.
"""

from __future__ import annotations

import logging
import time

from orchestrator.state import ContextPacket, EncounterState, EncounterStatus

logger = logging.getLogger(__name__)


def context_node(state: EncounterState) -> dict:
    """Load pre-encounter patient context (stub)."""
    logger.info("context_node: start", extra={"encounter_id": state.encounter_id})
    t0 = time.monotonic_ns()

    # --- stub: create an empty context packet ---------------------------
    context_packet = ContextPacket(
        source="manual",
        # Real node fetches from EHR via MCP EHR server
    )

    elapsed_ms = (time.monotonic_ns() - t0) // 1_000_000

    logger.info("context_node: done", extra={"encounter_id": state.encounter_id, "elapsed_ms": elapsed_ms})

    return {
        "status": EncounterStatus.CONTEXT_LOADING,
        "context_packet": context_packet,
        "metrics": state.metrics.model_copy(
            update={
                "context_load_ms": elapsed_ms,
                "nodes_completed": state.metrics.nodes_completed + ["context"],
            }
        ),
    }
