"""
tests/unit/test_ehr_config.py — Tests for EHRConfig in deployment configuration.

Validates EHRConfig defaults, FHIR settings, DeploymentConfig integration,
and YAML parsing of the ehr section.
"""
from __future__ import annotations

import yaml

from config.deployment import (
    DeploymentConfig,
    EHRConfig,
    _flatten_yaml,
)


# ---------------------------------------------------------------------------
# EHRConfig model defaults
# ---------------------------------------------------------------------------
class TestEHRConfigDefaults:
    def test_default_adapter_is_stub(self):
        cfg = EHRConfig()
        assert cfg.adapter == "stub"

    def test_default_fhir_base_url_empty(self):
        cfg = EHRConfig()
        assert cfg.fhir_base_url == ""

    def test_default_fhir_vendor_empty(self):
        cfg = EHRConfig()
        assert cfg.fhir_vendor == ""

    def test_default_fhir_client_id_empty(self):
        cfg = EHRConfig()
        assert cfg.fhir_client_id == ""

    def test_default_fhir_client_secret_env(self):
        cfg = EHRConfig()
        assert cfg.fhir_client_secret_env == "AI_SCRIBE_EHR_CLIENT_SECRET"

    def test_default_fhir_scopes(self):
        cfg = EHRConfig()
        assert cfg.fhir_scopes == [
            "patient/*.read",
            "patient/DocumentReference.write",
        ]


# ---------------------------------------------------------------------------
# EHRConfig with FHIR settings
# ---------------------------------------------------------------------------
class TestEHRConfigFHIR:
    def test_fhir_adapter(self):
        cfg = EHRConfig(
            adapter="fhir",
            fhir_base_url="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
            fhir_vendor="epic",
            fhir_client_id="my-client-id",
            fhir_client_secret_env="MY_SECRET_ENV",
            fhir_scopes=["patient/*.read", "launch/patient"],
        )
        assert cfg.adapter == "fhir"
        assert cfg.fhir_base_url == "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
        assert cfg.fhir_vendor == "epic"
        assert cfg.fhir_client_id == "my-client-id"
        assert cfg.fhir_client_secret_env == "MY_SECRET_ENV"
        assert cfg.fhir_scopes == ["patient/*.read", "launch/patient"]

    def test_cerner_vendor(self):
        cfg = EHRConfig(adapter="fhir", fhir_vendor="cerner")
        assert cfg.fhir_vendor == "cerner"

    def test_athena_vendor(self):
        cfg = EHRConfig(adapter="fhir", fhir_vendor="athena")
        assert cfg.fhir_vendor == "athena"


# ---------------------------------------------------------------------------
# DeploymentConfig includes ehr field
# ---------------------------------------------------------------------------
class TestDeploymentConfigEHR:
    def test_deployment_config_has_ehr(self):
        cfg = DeploymentConfig()
        assert hasattr(cfg, "ehr")
        assert isinstance(cfg.ehr, EHRConfig)

    def test_deployment_config_ehr_defaults(self):
        cfg = DeploymentConfig()
        assert cfg.ehr.adapter == "stub"
        assert cfg.ehr.fhir_base_url == ""

    def test_deployment_config_with_custom_ehr(self):
        cfg = DeploymentConfig(
            ehr=EHRConfig(adapter="fhir", fhir_vendor="epic")
        )
        assert cfg.ehr.adapter == "fhir"
        assert cfg.ehr.fhir_vendor == "epic"


# ---------------------------------------------------------------------------
# YAML parsing picks up ehr section
# ---------------------------------------------------------------------------
class TestFlattenYamlEHR:
    def test_empty_yaml_gives_default_ehr(self):
        result = _flatten_yaml({})
        cfg = DeploymentConfig(**result)
        assert cfg.ehr.adapter == "stub"

    def test_ehr_section_parsed(self):
        raw = {
            "ehr": {
                "adapter": "fhir",
                "fhir": {
                    "base_url": "https://fhir.epic.com/R4",
                    "vendor": "epic",
                    "client_id": "test-client",
                    "client_secret_env": "TEST_SECRET",
                    "scopes": ["patient/*.read"],
                },
            }
        }
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.ehr.adapter == "fhir"
        assert cfg.ehr.fhir_base_url == "https://fhir.epic.com/R4"
        assert cfg.ehr.fhir_vendor == "epic"
        assert cfg.ehr.fhir_client_id == "test-client"
        assert cfg.ehr.fhir_client_secret_env == "TEST_SECRET"
        assert cfg.ehr.fhir_scopes == ["patient/*.read"]

    def test_ehr_stub_only_adapter(self):
        raw = {"ehr": {"adapter": "stub"}}
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.ehr.adapter == "stub"
        assert cfg.ehr.fhir_base_url == ""

    def test_ehr_section_from_full_yaml(self):
        """Parse a realistic YAML snippet with ehr alongside other sections."""
        yaml_str = """
server:
  role: "provider-facing"
ehr:
  adapter: "fhir"
  fhir:
    base_url: "https://fhir.cerner.com/R4"
    vendor: "cerner"
    client_id: "cerner-client"
    client_secret_env: "CERNER_SECRET"
    scopes:
      - "patient/*.read"
      - "patient/DocumentReference.write"
"""
        raw = yaml.safe_load(yaml_str)
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.role.value == "provider-facing"
        assert cfg.ehr.adapter == "fhir"
        assert cfg.ehr.fhir_vendor == "cerner"
        assert cfg.ehr.fhir_client_id == "cerner-client"
        assert len(cfg.ehr.fhir_scopes) == 2
