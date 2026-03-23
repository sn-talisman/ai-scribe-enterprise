"""
tests/unit/test_incremental_sync.py — Tests for IncrementalSync, ConflictResolver,
and OutputSyncEnhanced configuration model.

Covers:
- IncrementalSync.should_fetch timestamp comparison logic
- IncrementalSync.fetch_if_newer HTTP header behavior
- ConflictResolver strategies (keep_both, keep_remote, keep_local)
- OutputSyncEnhanced Pydantic model defaults and integration with DeploymentConfig
- _flatten_yaml parsing of output_sync_enhanced section
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.sync import ConflictResolver, IncrementalSync
from config.deployment import (
    DeploymentConfig,
    OutputSyncEnhanced,
    _flatten_yaml,
)


# ---------------------------------------------------------------------------
# IncrementalSync.should_fetch
# ---------------------------------------------------------------------------

class TestIncrementalSyncShouldFetch:
    """IncrementalSync.should_fetch returns True only when remote is strictly newer."""

    def test_returns_true_when_local_missing(self, tmp_path: Path):
        missing = tmp_path / "no_such_file.md"
        remote_ts = format_datetime(datetime(2026, 3, 15, tzinfo=timezone.utc), usegmt=True)
        assert IncrementalSync.should_fetch(missing, remote_ts) is True

    def test_returns_true_when_remote_is_newer(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("old content")
        # Set local mtime to a known past time
        old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(local, (old_ts, old_ts))

        remote_ts = format_datetime(datetime(2026, 6, 1, tzinfo=timezone.utc), usegmt=True)
        assert IncrementalSync.should_fetch(local, remote_ts) is True

    def test_returns_false_when_local_is_newer(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("fresh content")
        # Set local mtime to a future time
        future_ts = datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(local, (future_ts, future_ts))

        remote_ts = format_datetime(datetime(2026, 1, 1, tzinfo=timezone.utc), usegmt=True)
        assert IncrementalSync.should_fetch(local, remote_ts) is False

    def test_returns_false_when_timestamps_equal(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("content")
        exact_dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        os.utime(local, (exact_dt.timestamp(), exact_dt.timestamp()))

        remote_ts = format_datetime(exact_dt, usegmt=True)
        assert IncrementalSync.should_fetch(local, remote_ts) is False

    def test_returns_true_on_unparseable_remote_timestamp(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("content")
        assert IncrementalSync.should_fetch(local, "not-a-date") is True


# ---------------------------------------------------------------------------
# IncrementalSync.fetch_if_newer
# ---------------------------------------------------------------------------

class TestIncrementalSyncFetchIfNewer:
    """IncrementalSync.fetch_if_newer sends If-Modified-Since and handles 200/304."""

    async def test_fetches_on_200(self, tmp_path: Path):
        local = tmp_path / "note.md"
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "remote content"
        resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=resp)

        result = await IncrementalSync.fetch_if_newer(client, "/file", local)
        assert result is True
        assert local.read_text() == "remote content"

    async def test_skips_on_304(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("local content")

        resp = MagicMock()
        resp.status_code = 304

        client = AsyncMock()
        client.get = AsyncMock(return_value=resp)

        result = await IncrementalSync.fetch_if_newer(client, "/file", local)
        assert result is False
        assert local.read_text() == "local content"

    async def test_sends_if_modified_since_when_local_exists(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("existing")

        resp = MagicMock()
        resp.status_code = 304

        client = AsyncMock()
        client.get = AsyncMock(return_value=resp)

        await IncrementalSync.fetch_if_newer(client, "/file", local)

        call_kwargs = client.get.call_args[1]
        assert "If-Modified-Since" in call_kwargs["headers"]

    async def test_no_if_modified_since_when_local_missing(self, tmp_path: Path):
        local = tmp_path / "missing.md"

        resp = MagicMock()
        resp.status_code = 200
        resp.text = "new"
        resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=resp)

        await IncrementalSync.fetch_if_newer(client, "/file", local)

        call_kwargs = client.get.call_args[1]
        assert call_kwargs["headers"] == {}

    async def test_returns_false_on_error(self, tmp_path: Path):
        local = tmp_path / "note.md"

        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("network error"))

        result = await IncrementalSync.fetch_if_newer(client, "/file", local)
        assert result is False


# ---------------------------------------------------------------------------
# ConflictResolver
# ---------------------------------------------------------------------------

class TestConflictResolverKeepBoth:
    """ConflictResolver 'keep_both' renames local to .local and writes remote."""

    def test_creates_local_backup_and_writes_remote(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("local version")

        resolver = ConflictResolver(strategy="keep_both")
        result = resolver.resolve(local, "remote version", "2026-06-01T00:00:00Z")

        assert result == local
        assert local.read_text() == "remote version"
        backup = tmp_path / "note.md.local"
        assert backup.exists()
        assert backup.read_text() == "local version"


class TestConflictResolverKeepRemote:
    """ConflictResolver 'keep_remote' overwrites local with remote."""

    def test_overwrites_local(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("local version")

        resolver = ConflictResolver(strategy="keep_remote")
        result = resolver.resolve(local, "remote version", "2026-06-01T00:00:00Z")

        assert result == local
        assert local.read_text() == "remote version"
        backup = tmp_path / "note.md.local"
        assert not backup.exists()


class TestConflictResolverKeepLocal:
    """ConflictResolver 'keep_local' keeps local unchanged."""

    def test_keeps_local_unchanged(self, tmp_path: Path):
        local = tmp_path / "note.md"
        local.write_text("local version")

        resolver = ConflictResolver(strategy="keep_local")
        result = resolver.resolve(local, "remote version", "2026-06-01T00:00:00Z")

        assert result == local
        assert local.read_text() == "local version"


# ---------------------------------------------------------------------------
# OutputSyncEnhanced model
# ---------------------------------------------------------------------------

class TestOutputSyncEnhancedDefaults:
    """OutputSyncEnhanced Pydantic model has correct defaults."""

    def test_defaults(self):
        model = OutputSyncEnhanced()
        assert model.websocket_enabled is True
        assert model.websocket_reconnect_interval == 30
        assert model.incremental is True
        assert model.conflict_strategy == "keep_both"

    def test_custom_values(self):
        model = OutputSyncEnhanced(
            websocket_enabled=False,
            websocket_reconnect_interval=60,
            incremental=False,
            conflict_strategy="keep_remote",
        )
        assert model.websocket_enabled is False
        assert model.websocket_reconnect_interval == 60
        assert model.incremental is False
        assert model.conflict_strategy == "keep_remote"


class TestOutputSyncEnhancedInDeploymentConfig:
    """OutputSyncEnhanced integrates with DeploymentConfig."""

    def test_default_in_deployment_config(self):
        cfg = DeploymentConfig()
        assert cfg.output_sync_enhanced.websocket_enabled is True
        assert cfg.output_sync_enhanced.incremental is True
        assert cfg.output_sync_enhanced.conflict_strategy == "keep_both"

    def test_custom_in_deployment_config(self):
        cfg = DeploymentConfig(
            output_sync_enhanced=OutputSyncEnhanced(
                websocket_enabled=False,
                conflict_strategy="keep_local",
            )
        )
        assert cfg.output_sync_enhanced.websocket_enabled is False
        assert cfg.output_sync_enhanced.conflict_strategy == "keep_local"


# ---------------------------------------------------------------------------
# _flatten_yaml parses output_sync_enhanced
# ---------------------------------------------------------------------------

class TestFlattenYamlOutputSyncEnhanced:
    """_flatten_yaml correctly parses the output_sync_enhanced section."""

    def test_parses_output_sync_enhanced(self):
        raw = {
            "output_sync_enhanced": {
                "websocket_enabled": False,
                "websocket_reconnect_interval": 45,
                "incremental": False,
                "conflict_strategy": "keep_remote",
            }
        }
        flat = _flatten_yaml(raw)
        assert flat["output_sync_enhanced"]["websocket_enabled"] is False
        assert flat["output_sync_enhanced"]["websocket_reconnect_interval"] == 45
        assert flat["output_sync_enhanced"]["incremental"] is False
        assert flat["output_sync_enhanced"]["conflict_strategy"] == "keep_remote"

    def test_missing_section_uses_defaults(self):
        flat = _flatten_yaml({})
        assert "output_sync_enhanced" not in flat
        # DeploymentConfig should still work with defaults
        cfg = DeploymentConfig(**flat)
        assert cfg.output_sync_enhanced.websocket_enabled is True

    def test_round_trip_through_deployment_config(self):
        raw = {
            "output_sync_enhanced": {
                "websocket_enabled": True,
                "websocket_reconnect_interval": 10,
                "incremental": True,
                "conflict_strategy": "keep_both",
            }
        }
        flat = _flatten_yaml(raw)
        cfg = DeploymentConfig(**flat)
        assert cfg.output_sync_enhanced.websocket_reconnect_interval == 10
