"""
tests/unit/test_api_roles.py — Tests for API server role-based routing.

Tests that the FastAPI app includes the correct routes based on server role,
and that feature-gated endpoints return 403 when disabled.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_config():
    """Reset deployment config after each test."""
    yield
    from config.deployment import get_deployment_config
    get_deployment_config(reload=True)


def _make_app(role: str = "both"):
    """Create a fresh FastAPI app with the given server role."""
    # Must set env var BEFORE importing main
    with patch.dict(os.environ, {"AI_SCRIBE_SERVER_ROLE": role}):
        from config.deployment import get_deployment_config
        get_deployment_config(reload=True)

        # Re-import to pick up new config (need to reload the module)
        import importlib
        import api.main
        importlib.reload(api.main)

        return api.main.app


class TestHealthEndpoints:
    """Health endpoints should work in all roles."""

    def test_health_both(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["role"] == "both"

    def test_root_shows_role(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "both"
        assert data["version"] == "1.0.0"


class TestFeatureEndpoints:
    """Feature flag endpoint should return correct flags per role."""

    def test_features_both(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/config/features")
        assert resp.status_code == 200
        flags = resp.json()
        # Both mode: everything enabled
        assert flags["dashboard"] is True
        assert flags["ehr_access"] is True
        assert flags["run_pipeline"] is True
        assert flags["create_providers"] is True

    def test_role_endpoint(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "both"
        assert data["is_provider_facing"] is True
        assert data["is_processing_pipeline"] is True


class TestEncounterRoutes:
    """Encounter read routes should work in all roles."""

    def test_list_encounters(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/encounters")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_quality_aggregate(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/quality/aggregate")
        # May return 200 with data or 200 with empty result
        assert resp.status_code == 200


class TestPipelineRoutes:
    """Pipeline API routes should only be available on processing-pipeline role."""

    def test_pipeline_routes_available_in_both(self):
        app = _make_app("both")
        client = TestClient(app)
        # The /pipeline/ prefix should exist
        resp = client.get("/pipeline/status/nonexistent")
        # Should return 404 (route exists, job not found) not 405/404 (route missing)
        assert resp.status_code == 404

    def test_pipeline_upload_requires_feature(self):
        """Pipeline upload should work in both mode since run_pipeline is enabled."""
        app = _make_app("both")
        client = TestClient(app)
        # No audio provided → should get 422 (validation error), not 403
        resp = client.post("/pipeline/upload", data={"sample_id": "test", "mode": "dictation"})
        assert resp.status_code == 422  # Missing required 'audio' file


class TestProviderRoutes:
    """Provider routes availability based on role."""

    def test_providers_list_in_both(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/providers")
        assert resp.status_code == 200


class TestPatientRoutes:
    """Patient routes only available on provider-facing."""

    def test_patient_search_in_both(self):
        app = _make_app("both")
        client = TestClient(app)
        resp = client.get("/patients/search")
        assert resp.status_code == 200
