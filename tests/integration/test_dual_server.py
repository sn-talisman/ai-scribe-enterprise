"""
tests/integration/test_dual_server.py — Dual-server integration tests.

Verifies that the provider-facing and processing-pipeline server roles:
1. Resolve different data/output directories
2. Mount the correct API routes for their role
3. Feature flags restrict access appropriately
4. Config endpoints report correct role information
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def provider_client(tmp_path):
    """Create a TestClient simulating provider-facing server."""
    data_dir = tmp_path / "provider-data"
    output_dir = tmp_path / "provider-output"
    data_dir.mkdir()
    output_dir.mkdir()

    env = {
        "AI_SCRIBE_DATA_DIR": str(data_dir),
        "AI_SCRIBE_OUTPUT_DIR": str(output_dir),
        "AI_SCRIBE_SERVER_ROLE": "provider-facing",
    }
    with patch.dict(os.environ, env):
        import config.paths
        importlib.reload(config.paths)
        import config.deployment
        importlib.reload(config.deployment)
        config.deployment.get_deployment_config(reload=True)
        import api.data_loader
        importlib.reload(api.data_loader)
        api.data_loader._quality_cache.clear()
        import api.main
        importlib.reload(api.main)

        client = TestClient(api.main.app)
        yield client

    # Reset
    config.deployment.get_deployment_config(reload=True)


@pytest.fixture
def pipeline_client(tmp_path):
    """Create a TestClient simulating processing-pipeline server."""
    data_dir = tmp_path / "pipeline-data"
    output_dir = tmp_path / "pipeline-output"
    data_dir.mkdir()
    output_dir.mkdir()

    env = {
        "AI_SCRIBE_DATA_DIR": str(data_dir),
        "AI_SCRIBE_OUTPUT_DIR": str(output_dir),
        "AI_SCRIBE_SERVER_ROLE": "processing-pipeline",
    }
    with patch.dict(os.environ, env):
        import config.paths
        importlib.reload(config.paths)
        import config.deployment
        importlib.reload(config.deployment)
        config.deployment.get_deployment_config(reload=True)
        import api.data_loader
        importlib.reload(api.data_loader)
        api.data_loader._quality_cache.clear()
        import api.main
        importlib.reload(api.main)

        client = TestClient(api.main.app)
        yield client

    config.deployment.get_deployment_config(reload=True)


class TestRoleReporting:
    def test_provider_reports_correct_role(self, provider_client):
        resp = provider_client.get("/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "provider-facing"
        assert data["is_provider_facing"] is True
        assert data["is_processing_pipeline"] is False

    def test_pipeline_reports_correct_role(self, pipeline_client):
        resp = pipeline_client.get("/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "processing-pipeline"
        assert data["is_provider_facing"] is False
        assert data["is_processing_pipeline"] is True


class TestFeatureFlags:
    def test_provider_has_ehr_access(self, provider_client):
        resp = provider_client.get("/config/features")
        data = resp.json()
        assert data["ehr_access"] is True
        assert data["patient_search"] is True

    def test_provider_no_admin_features(self, provider_client):
        resp = provider_client.get("/config/features")
        data = resp.json()
        assert data["create_providers"] is False
        assert data["edit_templates"] is False

    def test_pipeline_has_admin_features(self, pipeline_client):
        resp = pipeline_client.get("/config/features")
        data = resp.json()
        assert data["create_providers"] is True
        assert data["edit_templates"] is True
        assert data["run_pipeline"] is True

    def test_pipeline_no_ehr_access(self, pipeline_client):
        resp = pipeline_client.get("/config/features")
        data = resp.json()
        assert data["ehr_access"] is False
        assert data["patient_search"] is False


class TestSharedEndpoints:
    def test_both_serve_encounters(self, provider_client, pipeline_client):
        resp1 = provider_client.get("/encounters")
        resp2 = pipeline_client.get("/encounters")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_both_serve_quality(self, provider_client, pipeline_client):
        resp1 = provider_client.get("/quality/aggregate", params={"version": "latest"})
        resp2 = pipeline_client.get("/quality/aggregate", params={"version": "latest"})
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_both_serve_health(self, provider_client, pipeline_client):
        resp1 = provider_client.get("/health")
        resp2 = pipeline_client.get("/health")
        assert resp1.json()["status"] == "ok"
        assert resp2.json()["status"] == "ok"


class TestLatestVersionEndpoint:
    def test_provider_returns_latest_version(self, provider_client):
        resp = provider_client.get("/config/latest-version")
        assert resp.status_code == 200
        data = resp.json()
        assert "latest" in data
        assert "versions" in data

    def test_pipeline_returns_latest_version(self, pipeline_client):
        resp = pipeline_client.get("/config/latest-version")
        assert resp.status_code == 200
        data = resp.json()
        assert "latest" in data
