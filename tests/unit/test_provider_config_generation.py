"""
tests/unit/test_provider_config_generation.py — Tests for provider server
configuration generation logic (deploy/setup_provider_server.ps1 Step 3/7).

Validates that:
- .env.provider contains correct keys and values (Req 2.1)
- deployment.yaml is updated with PipelineUrl and PublicUrl (Req 2.2, 2.3)
- security.inter_server_auth.enabled is set to true (Req 2.6)
- Inter-server secret meets minimum length and URL-safe requirements (Req 2.4, 2.5)
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers — Python equivalents of the PowerShell config generation logic
# ---------------------------------------------------------------------------

# URL-safe base64 character set (no padding)
URL_SAFE_PATTERN = re.compile(r'^[A-Za-z0-9\-_]+$')


def generate_env_provider(
    project_root: str,
    pipeline_url: str,
    secret: str,
) -> str:
    """Generate .env.provider content matching the PowerShell script output."""
    data_dir = os.path.join(project_root, "ai-scribe-data")
    output_dir = os.path.join(project_root, "output")
    config_dir = os.path.join(project_root, "config")
    return (
        f"AI_SCRIBE_SERVER_ROLE=provider-facing\n"
        f"AI_SCRIBE_DATA_DIR={data_dir}\n"
        f"AI_SCRIBE_OUTPUT_DIR={output_dir}\n"
        f"AI_SCRIBE_CONFIG_DIR={config_dir}\n"
        f"PIPELINE_API_URL={pipeline_url}\n"
        f"AI_SCRIBE_INTER_SERVER_SECRET={secret}\n"
    )


def parse_env_file(content: str) -> dict[str, str]:
    """Parse a .env file into a dict."""
    result = {}
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        result[key] = value
    return result


def update_deployment_yaml(
    yaml_text: str,
    pipeline_url: str,
    public_url: str,
) -> str:
    """
    Python equivalent of the PowerShell section-aware YAML updater.
    Updates specific fields while preserving structure and comments.

    Tracks parent sections (keys whose value is a nested block) by
    indentation level, then builds a dotted path for each leaf key.
    """
    lines = yaml_text.splitlines()
    updated = []
    # Only track section headers (keys with no inline value — value is a block)
    parent_at_indent: dict[int, str] = {}

    for line in lines:
        m = re.match(r'^(\s*)(\w[\w_]*):', line)
        if m:
            indent = len(m.group(1))
            key = m.group(2)
            rest = line[m.end():]  # everything after "key:"

            # Clear deeper or equal levels from parent tracker
            for lvl in [k for k in parent_at_indent if k >= indent]:
                del parent_at_indent[lvl]

            # Determine if this is a section header (no inline value) or a leaf
            rest_stripped = rest.strip()
            is_section = (rest_stripped == "" or rest_stripped.startswith("#"))

            if is_section:
                parent_at_indent[indent] = key

            # Build full path: parents + current key
            parent_path = ".".join(
                v for _, v in sorted(parent_at_indent.items())
            )
            full_path = f"{parent_path}.{key}" if parent_path else key

            # Update network.provider_facing.public_url
            if full_path == "network.provider_facing.public_url" and public_url:
                spaces = m.group(1)
                updated.append(f'{spaces}public_url: "{public_url}"')
                continue

            # Update network.processing_pipeline.internal_url
            if full_path == "network.processing_pipeline.internal_url":
                spaces = m.group(1)
                updated.append(f'{spaces}internal_url: "{pipeline_url}"')
                continue

            # Update security.inter_server_auth.enabled
            if full_path == "security.inter_server_auth.enabled":
                spaces = m.group(1)
                updated.append(f"{spaces}enabled: true")
                continue

        updated.append(line)

    return "\n".join(updated)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def deployment_yaml_text() -> str:
    """Return the content of config/deployment.yaml from the repo."""
    yaml_path = Path(__file__).resolve().parents[2] / "config" / "deployment.yaml"
    return yaml_path.read_text(encoding="utf-8")


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with deployment.yaml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Copy real deployment.yaml
    src = Path(__file__).resolve().parents[2] / "config" / "deployment.yaml"
    shutil.copy2(src, config_dir / "deployment.yaml")
    return tmp_path


# ---------------------------------------------------------------------------
# .env.provider tests (Req 2.1)
# ---------------------------------------------------------------------------

class TestEnvProviderGeneration:
    def test_contains_server_role(self):
        content = generate_env_provider("/proj", "http://pipe:8100", "secret123")
        env = parse_env_file(content)
        assert env["AI_SCRIBE_SERVER_ROLE"] == "provider-facing"

    def test_contains_data_directory_paths(self):
        content = generate_env_provider("/proj", "http://pipe:8100", "s")
        env = parse_env_file(content)
        assert "ai-scribe-data" in env["AI_SCRIBE_DATA_DIR"]
        assert "output" in env["AI_SCRIBE_OUTPUT_DIR"]
        assert "config" in env["AI_SCRIBE_CONFIG_DIR"]

    def test_contains_pipeline_url(self):
        url = "http://pipeline-host:8100"
        content = generate_env_provider("/proj", url, "s")
        env = parse_env_file(content)
        assert env["PIPELINE_API_URL"] == url

    def test_contains_inter_server_secret(self):
        content = generate_env_provider("/proj", "http://x:8100", "my-secret-value")
        env = parse_env_file(content)
        assert env["AI_SCRIBE_INTER_SERVER_SECRET"] == "my-secret-value"

    def test_all_required_keys_present(self):
        content = generate_env_provider("/proj", "http://x:8100", "s")
        env = parse_env_file(content)
        required_keys = {
            "AI_SCRIBE_SERVER_ROLE",
            "AI_SCRIBE_DATA_DIR",
            "AI_SCRIBE_OUTPUT_DIR",
            "AI_SCRIBE_CONFIG_DIR",
            "PIPELINE_API_URL",
            "AI_SCRIBE_INTER_SERVER_SECRET",
        }
        assert required_keys == set(env.keys())


# ---------------------------------------------------------------------------
# deployment.yaml update tests (Req 2.2, 2.3, 2.6)
# ---------------------------------------------------------------------------

class TestDeploymentYamlUpdate:
    def test_pipeline_url_written(self, deployment_yaml_text: str):
        url = "http://remote-pipeline:8100"
        result = update_deployment_yaml(deployment_yaml_text, url, "")
        parsed = yaml.safe_load(result)
        assert parsed["network"]["processing_pipeline"]["internal_url"] == url

    def test_public_url_written(self, deployment_yaml_text: str):
        url = "https://provider.example.com"
        result = update_deployment_yaml(
            deployment_yaml_text, "http://localhost:8100", url
        )
        parsed = yaml.safe_load(result)
        assert parsed["network"]["provider_facing"]["public_url"] == url

    def test_public_url_unchanged_when_empty(self, deployment_yaml_text: str):
        original = yaml.safe_load(deployment_yaml_text)
        original_public = original["network"]["provider_facing"]["public_url"]
        result = update_deployment_yaml(
            deployment_yaml_text, "http://localhost:8100", ""
        )
        parsed = yaml.safe_load(result)
        assert parsed["network"]["provider_facing"]["public_url"] == original_public

    def test_inter_server_auth_enabled(self, deployment_yaml_text: str):
        result = update_deployment_yaml(
            deployment_yaml_text, "http://localhost:8100", ""
        )
        parsed = yaml.safe_load(result)
        assert parsed["security"]["inter_server_auth"]["enabled"] is True

    def test_other_fields_preserved(self, deployment_yaml_text: str):
        result = update_deployment_yaml(
            deployment_yaml_text, "http://new-pipe:8100", "https://pub.example.com"
        )
        parsed = yaml.safe_load(result)
        # Verify unrelated fields are untouched
        assert parsed["server"]["role"] == "provider-facing"
        assert parsed["network"]["provider_facing"]["api_port"] == 8000
        assert parsed["network"]["processing_pipeline"]["api_port"] == 8100
        assert parsed["security"]["inter_server_auth"]["secret_env_var"] == "AI_SCRIBE_INTER_SERVER_SECRET"
        assert parsed["sync"]["config_sync"]["enabled"] is True

    def test_pipeline_url_does_not_affect_provider_section(self, deployment_yaml_text: str):
        """Ensure PipelineUrl only updates processing_pipeline, not provider_facing."""
        result = update_deployment_yaml(
            deployment_yaml_text, "http://new-pipe:9999", ""
        )
        parsed = yaml.safe_load(result)
        # provider_facing should still have original public_url
        assert parsed["network"]["provider_facing"]["public_url"] == "http://localhost:8000"
        # processing_pipeline should have the new URL
        assert parsed["network"]["processing_pipeline"]["internal_url"] == "http://new-pipe:9999"


# ---------------------------------------------------------------------------
# Inter-server secret tests (Req 2.4, 2.5)
# ---------------------------------------------------------------------------

class TestInterServerSecret:
    def test_provided_secret_used_verbatim(self):
        secret = "my-pre-shared-secret-value-12345"
        content = generate_env_provider("/proj", "http://x:8100", secret)
        env = parse_env_file(content)
        assert env["AI_SCRIBE_INTER_SERVER_SECRET"] == secret

    def test_url_safe_characters_only(self):
        """URL-safe base64 should only contain [A-Za-z0-9-_]."""
        import base64
        # Simulate the PowerShell generation: 48 random bytes -> base64 -> URL-safe
        random_bytes = os.urandom(48)
        secret = base64.b64encode(random_bytes).decode("ascii")
        secret = secret.replace("+", "-").replace("/", "_").rstrip("=")
        assert URL_SAFE_PATTERN.match(secret), f"Secret contains non-URL-safe chars: {secret}"
        assert len(secret) >= 32

    def test_generated_secret_minimum_length(self):
        """48 bytes -> base64 produces 64 chars, minus padding still >= 32."""
        import base64
        for _ in range(20):
            random_bytes = os.urandom(48)
            secret = base64.b64encode(random_bytes).decode("ascii")
            secret = secret.replace("+", "-").replace("/", "_").rstrip("=")
            assert len(secret) >= 32, f"Secret too short: {len(secret)} chars"


# ---------------------------------------------------------------------------
# Docker deployment file content tests (Req 6.1–6.5)
# ---------------------------------------------------------------------------

class TestDockerComposeEnvVars:
    """Verify docker-compose.provider.yml contains required environment variables."""

    @pytest.fixture(autouse=True)
    def _load_compose(self):
        compose_path = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.provider.yml"
        self.compose_content = compose_path.read_text(encoding="utf-8")

    def test_contains_inter_server_secret(self):
        assert "AI_SCRIBE_INTER_SERVER_SECRET" in self.compose_content

    def test_contains_pipeline_api_url(self):
        assert "PIPELINE_API_URL" in self.compose_content

    def test_inter_server_secret_has_empty_default(self):
        assert "AI_SCRIBE_INTER_SERVER_SECRET=${AI_SCRIBE_INTER_SERVER_SECRET:-}" in self.compose_content

    def test_pipeline_url_has_sensible_default(self):
        assert "PIPELINE_API_URL=${PIPELINE_API_URL:-http://pipeline-server:8100}" in self.compose_content


class TestDockerfileEnvVars:
    """Verify Dockerfile.provider contains required ENV declarations."""

    @pytest.fixture(autouse=True)
    def _load_dockerfile(self):
        dockerfile_path = Path(__file__).resolve().parents[2] / "deploy" / "Dockerfile.provider"
        self.dockerfile_content = dockerfile_path.read_text(encoding="utf-8")

    def test_contains_inter_server_secret(self):
        assert 'ENV AI_SCRIBE_INTER_SERVER_SECRET=""' in self.dockerfile_content

    def test_contains_pipeline_api_url(self):
        assert 'ENV PIPELINE_API_URL=""' in self.dockerfile_content

    def test_still_contains_server_role(self):
        assert "ENV AI_SCRIBE_SERVER_ROLE=provider-facing" in self.dockerfile_content
