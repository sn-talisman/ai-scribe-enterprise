"""
api/routes/providers.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api import data_loader as dl
from api.models import ProviderSummary

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=list[ProviderSummary])
def list_providers():
    providers = dl.list_providers()
    return [ProviderSummary(**p) for p in providers]


@router.get("/{provider_id}")
def get_provider(provider_id: str):
    provider = dl.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    return provider


@router.get("/{provider_id}/quality-trend")
def get_quality_trend(provider_id: str):
    provider = dl.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

    history = provider.get("quality_history", [])
    scores = provider.get("quality_scores", {})

    # Build chart-ready data: [{version, score, date, samples}]
    trend = []
    for v in ["v1", "v2", "v3", "v4"]:
        if v in scores:
            # Find matching history entry
            entry = next((h for h in history if h.get("version") == v), None)
            trend.append({
                "version": v,
                "score": scores[v],
                "date": entry.get("date") if entry else None,
                "samples": entry.get("samples") if entry else None,
            })

    return {"provider_id": provider_id, "trend": trend}
