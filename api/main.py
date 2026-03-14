"""
api/main.py — FastAPI application entry point.

Start with:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import encounters, patients, providers, quality, specialties, templates
from api.ws import session_events

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ai_scribe_api_starting")
    yield
    log.info("ai_scribe_api_shutdown")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Scribe Enterprise API",
    description=(
        "REST + WebSocket API for the AI medical scribe pipeline. "
        "Exposes encounter data, generated notes, quality scores, and provider profiles."
    ),
    version="0.9.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(encounters.router)
app.include_router(patients.router)
app.include_router(providers.router)
app.include_router(quality.router)
app.include_router(specialties.router)
app.include_router(templates.router)
app.include_router(session_events.router)


@app.get("/", tags=["health"])
def root():
    return {
        "service": "AI Scribe Enterprise API",
        "version": "0.9.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
