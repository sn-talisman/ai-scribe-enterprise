"""
tests/unit/test_branding_config.py — Tests for BrandingConfig in deployment configuration.

Validates BrandingConfig defaults, custom values, DeploymentConfig integration,
and YAML parsing of the branding section.
"""
from __future__ import annotations

import yaml

from config.deployment import (
    BrandingConfig,
    DeploymentConfig,
    _flatten_yaml,
)


# ---------------------------------------------------------------------------
# BrandingConfig model defaults
# ---------------------------------------------------------------------------
class TestBrandingConfigDefaults:
    def test_default_practice_name(self):
        cfg = BrandingConfig()
        assert cfg.practice_name == "AI Scribe"

    def test_default_logo_url_empty(self):
        cfg = BrandingConfig()
        assert cfg.logo_url == ""

    def test_default_primary_color(self):
        cfg = BrandingConfig()
        assert cfg.primary_color == "#1a5276"


# ---------------------------------------------------------------------------
# BrandingConfig with custom values
# ---------------------------------------------------------------------------
class TestBrandingConfigCustom:
    def test_custom_practice_name(self):
        cfg = BrandingConfig(
            practice_name="Orthopedic Associates",
            logo_url="/branding/logo.png",
            primary_color="#2c3e50",
        )
        assert cfg.practice_name == "Orthopedic Associates"
        assert cfg.logo_url == "/branding/logo.png"
        assert cfg.primary_color == "#2c3e50"

    def test_partial_override(self):
        cfg = BrandingConfig(practice_name="My Clinic")
        assert cfg.practice_name == "My Clinic"
        assert cfg.logo_url == ""
        assert cfg.primary_color == "#1a5276"


# ---------------------------------------------------------------------------
# DeploymentConfig includes branding field
# ---------------------------------------------------------------------------
class TestDeploymentConfigBranding:
    def test_deployment_config_has_branding(self):
        cfg = DeploymentConfig()
        assert hasattr(cfg, "branding")
        assert isinstance(cfg.branding, BrandingConfig)

    def test_deployment_config_branding_defaults(self):
        cfg = DeploymentConfig()
        assert cfg.branding.practice_name == "AI Scribe"
        assert cfg.branding.logo_url == ""
        assert cfg.branding.primary_color == "#1a5276"

    def test_deployment_config_with_custom_branding(self):
        cfg = DeploymentConfig(
            branding=BrandingConfig(
                practice_name="Orthopedic Associates",
                logo_url="/branding/logo.png",
            )
        )
        assert cfg.branding.practice_name == "Orthopedic Associates"
        assert cfg.branding.logo_url == "/branding/logo.png"


# ---------------------------------------------------------------------------
# _flatten_yaml parses branding section
# ---------------------------------------------------------------------------
class TestFlattenYamlBranding:
    def test_empty_yaml_gives_default_branding(self):
        result = _flatten_yaml({})
        cfg = DeploymentConfig(**result)
        assert cfg.branding.practice_name == "AI Scribe"
        assert cfg.branding.logo_url == ""
        assert cfg.branding.primary_color == "#1a5276"

    def test_branding_section_parsed(self):
        raw = {
            "branding": {
                "practice_name": "Orthopedic Associates",
                "logo_url": "/branding/logo.png",
                "primary_color": "#2c3e50",
            }
        }
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.branding.practice_name == "Orthopedic Associates"
        assert cfg.branding.logo_url == "/branding/logo.png"
        assert cfg.branding.primary_color == "#2c3e50"

    def test_missing_branding_section_uses_defaults(self):
        raw = {"server": {"role": "provider-facing"}}
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.branding.practice_name == "AI Scribe"
        assert cfg.branding.logo_url == ""
        assert cfg.branding.primary_color == "#1a5276"

    def test_branding_from_full_yaml(self):
        """Parse a realistic YAML snippet with branding alongside other sections."""
        yaml_str = """
server:
  role: "provider-facing"
branding:
  practice_name: "Downtown Family Medicine"
  logo_url: "/assets/dfm-logo.svg"
  primary_color: "#3498db"
"""
        raw = yaml.safe_load(yaml_str)
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.role.value == "provider-facing"
        assert cfg.branding.practice_name == "Downtown Family Medicine"
        assert cfg.branding.logo_url == "/assets/dfm-logo.svg"
        assert cfg.branding.primary_color == "#3498db"

    def test_partial_branding_section(self):
        """Only practice_name set; logo_url and primary_color use defaults."""
        raw = {
            "branding": {
                "practice_name": "My Clinic",
            }
        }
        result = _flatten_yaml(raw)
        cfg = DeploymentConfig(**result)
        assert cfg.branding.practice_name == "My Clinic"
        assert cfg.branding.logo_url == ""
        assert cfg.branding.primary_color == "#1a5276"
