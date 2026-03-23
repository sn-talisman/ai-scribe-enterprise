"""
tests/unit/test_property_phase1.py — Property-based tests for Phase 1
(deployment automation) using Hypothesis.

Properties 1–9: version comparison, CPU-only filtering, dependency logging,
URL round-trip, inter-server secret, TLS cert paths, health check validation,
directory idempotency, NTFS ACL principals.

Minimum 100 examples per property (Hypothesis default is 100).
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import helpers from existing test modules (Python equivalents of PS logic)
# ---------------------------------------------------------------------------
from tests.unit.test_provider_config_generation import (
    generate_env_provider,
    parse_env_file,
    update_deployment_yaml,
    URL_SAFE_PATTERN,
)
from tests.unit.test_provider_directory_creation import (
    REQUIRED_SUBDIRS,
    create_data_directories,
    build_ntfs_acl_rules,
)
from tests.unit.test_provider_nginx_and_services import (
    generate_nginx_conf,
    validate_health_response,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

version_component = st.integers(min_value=0, max_value=9999)
version_string = st.tuples(version_component, version_component, version_component).map(
    lambda t: f"{t[0]}.{t[1]}.{t[2]}"
)

# GPU package names that must be filtered out
GPU_PACKAGES = ["cuda-runtime", "torch-gpu", "whisperx", "nvidia-smi", "triton"]
safe_pkg_name = st.from_regex(r"[a-z][a-z0-9\-]{0,30}", fullmatch=True).filter(
    lambda s: not any(s.startswith(g.split("-")[0]) for g in ["cuda", "nvidia"])
    and s not in GPU_PACKAGES
)
gpu_pkg = st.sampled_from(GPU_PACKAGES)

url_scheme = st.sampled_from(["http", "https"])
url_host = st.from_regex(r"[a-z][a-z0-9\-]{1,20}\.[a-z]{2,4}", fullmatch=True)
url_port = st.integers(min_value=1024, max_value=65535)
url_strategy = st.builds(lambda s, h, p: f"{s}://{h}:{p}", url_scheme, url_host, url_port)

# Windows-style and Unix-style file paths for TLS certs
file_path_segment = st.from_regex(r"[a-zA-Z0-9_\-]{1,15}", fullmatch=True)
unix_path = st.lists(file_path_segment, min_size=2, max_size=5).map(lambda parts: "/" + "/".join(parts))
win_path = st.lists(file_path_segment, min_size=2, max_size=5).map(
    lambda parts: "C:\\" + "\\".join(parts)
)
cert_path = st.one_of(unix_path, win_path)

# Dependency names and version strings for error logging
dep_name = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-_.]{0,30}", fullmatch=True)
dep_version = version_string

# Windows usernames for NTFS ACL tests
win_domain = st.from_regex(r"[A-Z]{2,10}", fullmatch=True)
win_user = st.from_regex(r"[a-z_][a-z0-9_]{1,15}", fullmatch=True)
win_account = st.builds(lambda d, u: f"{d}\\{u}", win_domain, win_user)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compare_version(a: str, b: str) -> int:
    """Numeric semantic version comparison (Python equivalent of PS Compare-Version)."""
    pa = [int(x) for x in a.split(".")]
    pb = [int(x) for x in b.split(".")]
    for x, y in zip(pa, pb):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def get_cpu_only_packages(packages: list[str]) -> list[str]:
    """Filter out GPU-specific packages (Python equivalent of PS Get-CpuOnlyPackages)."""
    gpu_prefixes = ("cuda", "torch-gpu", "whisperx", "nvidia-", "nvidia_", "triton")
    return [p for p in packages if not any(p.startswith(g) or p == g for g in gpu_prefixes)]


def format_dependency_error(name: str, version: str) -> str:
    """Structured error message for dependency failures."""
    return f"Dependency check failed: {name} requires version {version}"


def generate_inter_server_secret() -> str:
    """Generate a URL-safe secret >= 32 chars (mirrors PS logic)."""
    raw = os.urandom(48)
    secret = base64.b64encode(raw).decode("ascii")
    return secret.replace("+", "-").replace("/", "_").rstrip("=")


# ===========================================================================
# Property 1: Version string comparison is numeric, not lexicographic
# ===========================================================================

class TestPropertyVersionComparison:
    """Property 1: Semantic version comparison uses numeric ordering."""

    @given(a=version_string, b=version_string)
    @settings(max_examples=200)
    def test_reflexive(self, a: str, b: str):
        """compare_version(a, a) == 0 for all versions."""
        assert compare_version(a, a) == 0

    @given(a=version_string, b=version_string)
    @settings(max_examples=200)
    def test_antisymmetric(self, a: str, b: str):
        """If a < b then b > a (and vice versa)."""
        result_ab = compare_version(a, b)
        result_ba = compare_version(b, a)
        assert result_ab == -result_ba

    @given(
        major=version_component,
        minor=version_component,
        patch=version_component,
    )
    @settings(max_examples=200)
    def test_numeric_not_lexicographic(self, major: int, minor: int, patch: int):
        """9.0.0 < 10.0.0 numerically (lexicographic would say 9 > 1)."""
        assume(major < 9999)
        a = f"{major}.{minor}.{patch}"
        b = f"{major + 1}.{minor}.{patch}"
        assert compare_version(a, b) == -1

    @given(a=version_string, b=version_string, c=version_string)
    @settings(max_examples=200)
    def test_transitive(self, a: str, b: str, c: str):
        """If a <= b and b <= c then a <= c."""
        ab = compare_version(a, b)
        bc = compare_version(b, c)
        ac = compare_version(a, c)
        if ab <= 0 and bc <= 0:
            assert ac <= 0


# ===========================================================================
# Property 2: CPU-only package filtering
# ===========================================================================

class TestPropertyCpuOnlyFiltering:
    """Property 2: Filtered output never contains GPU packages and is a subset of input."""

    @given(
        safe=st.lists(safe_pkg_name, min_size=0, max_size=20),
        gpus=st.lists(gpu_pkg, min_size=0, max_size=5),
    )
    @settings(max_examples=200)
    def test_no_gpu_packages_in_output(self, safe: list[str], gpus: list[str]):
        mixed = safe + gpus
        filtered = get_cpu_only_packages(mixed)
        for pkg in filtered:
            assert pkg not in GPU_PACKAGES

    @given(
        safe=st.lists(safe_pkg_name, min_size=0, max_size=20),
        gpus=st.lists(gpu_pkg, min_size=0, max_size=5),
    )
    @settings(max_examples=200)
    def test_output_is_subset_of_input(self, safe: list[str], gpus: list[str]):
        mixed = safe + gpus
        filtered = get_cpu_only_packages(mixed)
        for pkg in filtered:
            assert pkg in mixed

    @given(safe=st.lists(safe_pkg_name, min_size=1, max_size=20))
    @settings(max_examples=200)
    def test_safe_packages_preserved(self, safe: list[str]):
        """If no GPU packages are present, all packages survive filtering."""
        filtered = get_cpu_only_packages(safe)
        assert set(filtered) == set(safe)


# ===========================================================================
# Property 3: Dependency failure produces structured error
# ===========================================================================

class TestPropertyDependencyError:
    """Property 3: Error messages always contain dependency name and version."""

    @given(name=dep_name, version=dep_version)
    @settings(max_examples=200)
    def test_error_contains_name(self, name: str, version: str):
        msg = format_dependency_error(name, version)
        assert name in msg

    @given(name=dep_name, version=dep_version)
    @settings(max_examples=200)
    def test_error_contains_version(self, name: str, version: str):
        msg = format_dependency_error(name, version)
        assert version in msg

    @given(name=dep_name, version=dep_version)
    @settings(max_examples=200)
    def test_error_is_nonempty_string(self, name: str, version: str):
        msg = format_dependency_error(name, version)
        assert isinstance(msg, str) and len(msg) > 0


# ===========================================================================
# Property 4: CLI URL arguments round-trip to deployment config
# ===========================================================================

class TestPropertyUrlRoundTrip:
    """Property 4: URLs written to deployment.yaml appear at correct YAML paths."""

    @pytest.fixture(autouse=True)
    def _load_yaml(self):
        yaml_path = Path(__file__).resolve().parents[2] / "config" / "deployment.yaml"
        self.yaml_text = yaml_path.read_text(encoding="utf-8")

    @given(pipeline_url=url_strategy)
    @settings(max_examples=200)
    def test_pipeline_url_round_trips(self, pipeline_url: str):
        result = update_deployment_yaml(self.yaml_text, pipeline_url, "")
        parsed = yaml.safe_load(result)
        assert parsed["network"]["processing_pipeline"]["internal_url"] == pipeline_url

    @given(public_url=url_strategy)
    @settings(max_examples=200)
    def test_public_url_round_trips(self, public_url: str):
        result = update_deployment_yaml(self.yaml_text, "http://localhost:8100", public_url)
        parsed = yaml.safe_load(result)
        assert parsed["network"]["provider_facing"]["public_url"] == public_url

    @given(pipeline_url=url_strategy, public_url=url_strategy)
    @settings(max_examples=200)
    def test_both_urls_independent(self, pipeline_url: str, public_url: str):
        result = update_deployment_yaml(self.yaml_text, pipeline_url, public_url)
        parsed = yaml.safe_load(result)
        assert parsed["network"]["processing_pipeline"]["internal_url"] == pipeline_url
        assert parsed["network"]["provider_facing"]["public_url"] == public_url


# ===========================================================================
# Property 5: Inter-server secret generation and passthrough
# ===========================================================================

class TestPropertyInterServerSecret:
    """Property 5: Provided secrets appear verbatim; generated secrets are ≥32 chars, URL-safe."""

    @given(secret=st.from_regex(r"[A-Za-z0-9\-_]{32,64}", fullmatch=True))
    @settings(max_examples=200)
    def test_provided_secret_verbatim(self, secret: str):
        content = generate_env_provider("/proj", "http://x:8100", secret)
        env = parse_env_file(content)
        assert env["AI_SCRIBE_INTER_SERVER_SECRET"] == secret

    @given(data=st.data())
    @settings(max_examples=200)
    def test_generated_secret_min_length(self, data):
        secret = generate_inter_server_secret()
        assert len(secret) >= 32

    @given(data=st.data())
    @settings(max_examples=200)
    def test_generated_secret_url_safe(self, data):
        secret = generate_inter_server_secret()
        assert URL_SAFE_PATTERN.match(secret), f"Non-URL-safe chars in: {secret}"


# ===========================================================================
# Property 6: TLS certificate paths in nginx config
# ===========================================================================

class TestPropertyTlsCertPaths:
    """Property 6: ssl_certificate and ssl_certificate_key contain exact paths."""

    @given(cert=cert_path, key=cert_path)
    @settings(max_examples=200)
    def test_cert_path_appears(self, cert: str, key: str):
        conf = generate_nginx_conf(cert, key)
        normalized_cert = cert.replace("\\", "/")
        assert f"ssl_certificate     {normalized_cert}" in conf

    @given(cert=cert_path, key=cert_path)
    @settings(max_examples=200)
    def test_key_path_appears(self, cert: str, key: str):
        conf = generate_nginx_conf(cert, key)
        normalized_key = key.replace("\\", "/")
        assert f"ssl_certificate_key {normalized_key}" in conf

    @given(cert=cert_path, key=cert_path)
    @settings(max_examples=200)
    def test_no_backslashes_in_cert_directive(self, cert: str, key: str):
        conf = generate_nginx_conf(cert, key)
        # Extract the ssl_certificate line
        for line in conf.splitlines():
            if "ssl_certificate " in line and "ssl_certificate_key" not in line:
                assert "\\" not in line


# ===========================================================================
# Property 7: Health check response validation
# ===========================================================================

class TestPropertyHealthCheck:
    """Property 7: Validator returns True iff response has status == 'ok'."""

    @given(extra=st.dictionaries(
        st.from_regex(r"[a-z_]{1,10}", fullmatch=True).filter(lambda k: k != "status"),
        st.one_of(st.text(max_size=20), st.integers(), st.booleans(), st.none()),
        max_size=5,
    ))
    @settings(max_examples=200)
    def test_true_when_status_ok(self, extra: dict):
        response = {"status": "ok", **extra}
        assert validate_health_response(response) is True

    @given(status=st.one_of(
        st.text(max_size=20).filter(lambda s: s != "ok"),
        st.integers(),
        st.booleans(),
        st.none(),
    ))
    @settings(max_examples=200)
    def test_false_when_status_not_ok(self, status):
        assert validate_health_response({"status": status}) is False

    @given(response=st.one_of(
        st.none(),
        st.text(max_size=50),
        st.integers(),
        st.lists(st.dictionaries(st.text(max_size=5), st.text(max_size=5), max_size=2), max_size=3),
    ))
    @settings(max_examples=200)
    def test_false_for_non_dict(self, response):
        assert validate_health_response(response) is False


# ===========================================================================
# Property 8: Data directory creation is idempotent and non-destructive
# ===========================================================================

class TestPropertyDirectoryIdempotency:
    """Property 8: All dirs exist after creation; pre-existing files unchanged."""

    @given(
        file_names=st.lists(
            st.from_regex(r"[a-z]{1,10}\.(json|yaml|md|txt)", fullmatch=True),
            min_size=1,
            max_size=10,
        ),
        file_content=st.text(min_size=1, max_size=200).filter(lambda s: "\r" not in s),
    )
    @settings(max_examples=100)
    def test_idempotent_preserves_files(self, file_names: list[str], file_content: str):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # First creation
            create_data_directories(str(tmp_path))

            # Plant files in the first data directory
            target_dir = tmp_path / REQUIRED_SUBDIRS[0]
            planted = {}
            for fname in set(file_names):
                fpath = target_dir / fname
                fpath.write_text(file_content, encoding="utf-8")
                planted[str(fpath)] = file_content

            # Second creation (idempotent)
            create_data_directories(str(tmp_path))

            # All directories still exist
            for subdir in REQUIRED_SUBDIRS:
                assert (tmp_path / subdir).is_dir()

            # All planted files unchanged
            for fpath_str, expected in planted.items():
                assert Path(fpath_str).read_text(encoding="utf-8") == expected

    @given(runs=st.integers(min_value=2, max_value=5))
    @settings(max_examples=100)
    def test_multiple_runs_no_error(self, runs: int):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            for _ in range(runs):
                result = create_data_directories(tmp_dir)
                assert len(result) == 7


# ===========================================================================
# Property 9: NTFS ACL command targets correct principals
# ===========================================================================

class TestPropertyNtfsAcl:
    """Property 9: ACLs grant FullControl to exactly service account + SYSTEM."""

    @given(account=win_account)
    @settings(max_examples=200)
    def test_exactly_two_principals(self, account: str):
        rules = build_ntfs_acl_rules(account)
        assert len(rules) == 2

    @given(account=win_account)
    @settings(max_examples=200)
    def test_service_account_full_control(self, account: str):
        rules = build_ntfs_acl_rules(account)
        principals = {r["principal"] for r in rules}
        assert account in principals
        svc = [r for r in rules if r["principal"] == account][0]
        assert svc["rights"] == "FullControl"

    @given(account=win_account)
    @settings(max_examples=200)
    def test_system_full_control(self, account: str):
        rules = build_ntfs_acl_rules(account)
        sys_rules = [r for r in rules if r["principal"] == "NT AUTHORITY\\SYSTEM"]
        assert len(sys_rules) == 1
        assert sys_rules[0]["rights"] == "FullControl"

    @given(account=win_account)
    @settings(max_examples=200)
    def test_inheritance_removal(self, account: str):
        rules = build_ntfs_acl_rules(account)
        principals = {r["principal"] for r in rules}
        assert principals == {account, "NT AUTHORITY\\SYSTEM"}
        for r in rules:
            assert "ContainerInherit" in r["inheritance"]
            assert "ObjectInherit" in r["inheritance"]
