"""
api/routes/quality.py
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api import data_loader as dl

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/aggregate")
def get_aggregate(version: str = Query(dl.LATEST_VERSION)):
    """Aggregate quality stats for a pipeline version."""
    return dl.get_aggregate_quality(version)


@router.get("/trend")
def get_trend():
    """Quality scores across all versions (chart data)."""
    return {"trend": dl.get_quality_by_version()}


@router.get("/samples")
def get_sample_scores(
    version: str = Query(dl.LATEST_VERSION),
    mode: str = Query(None),
    min_score: float = Query(None),
):
    """Per-sample quality scores, filterable."""
    scores = dl.get_all_sample_scores(version)
    if mode:
        scores = [s for s in scores if s.get("mode") == mode]
    if min_score is not None:
        scores = [s for s in scores if s.get("overall") and s["overall"] >= min_score]
    return scores


@router.get("/dimensions")
def get_dimension_breakdown(version: str = Query(dl.LATEST_VERSION)):
    """Dimension averages for radar/bar chart."""
    agg = dl.get_aggregate_quality(version)
    dims = agg.get("dimensions", {})
    # Return as list for Recharts
    return [
        {"dimension": "Medical Accuracy", "score": dims.get("accuracy")},
        {"dimension": "Completeness", "score": dims.get("completeness")},
        {"dimension": "No Hallucination", "score": dims.get("no_hallucination")},
        {"dimension": "Structure", "score": dims.get("structure")},
        {"dimension": "Clinical Language", "score": dims.get("language")},
    ]


@router.get("/by-mode")
def get_quality_by_mode(version: str = Query(dl.LATEST_VERSION)):
    """Aggregate quality broken down by dictation vs ambient."""
    return dl.get_aggregate_quality_by_mode(version)


@router.get("/by-provider")
def get_quality_by_provider(version: str = Query(dl.LATEST_VERSION)):
    """Aggregate quality per provider."""
    return dl.get_aggregate_quality_by_provider(version)


@router.get("/batch/{version}")
def get_batch_stats(version: str):
    """Pipeline batch run stats (timing, ASR confidence, etc.)."""
    return dl.get_batch_stats(version)
