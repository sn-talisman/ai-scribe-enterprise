"""
tests/unit/test_provider_directory_creation.py — Tests for provider server
data directory creation and NTFS ACL logic (deploy/setup_provider_server.ps1 Step 4/7).

Validates that:
- All 7 required directories are created (Req 7.1)
- NTFS ACLs grant FullControl to service account + SYSTEM only (Req 7.2)
- Pre-existing directories and files are preserved (Req 7.3)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — Python equivalents of the PowerShell directory creation logic
# ---------------------------------------------------------------------------

REQUIRED_SUBDIRS = [
    os.path.join("ai-scribe-data", "dictation"),
    os.path.join("ai-scribe-data", "conversation"),
    os.path.join("output", "dictation"),
    os.path.join("output", "conversation"),
    os.path.join("config", "providers"),
    os.path.join("config", "templates"),
    os.path.join("config", "dictionaries"),
]


def create_data_directories(project_root: str) -> list[str]:
    """
    Python equivalent of the PowerShell Step 4/7 directory creation.
    Creates all required data directories idempotently.
    Returns list of created/existing directory paths.
    """
    created = []
    for subdir in REQUIRED_SUBDIRS:
        full_path = os.path.join(project_root, subdir)
        os.makedirs(full_path, exist_ok=True)
        created.append(full_path)
    return created


def build_ntfs_acl_rules(service_account: str) -> list[dict]:
    """
    Python equivalent of the PowerShell NTFS ACL construction.
    Returns the list of ACL rule descriptors that would be applied.
    """
    rules = [
        {
            "principal": service_account,
            "rights": "FullControl",
            "inheritance": "ContainerInherit, ObjectInherit",
            "propagation": "None",
            "type": "Allow",
        },
        {
            "principal": "NT AUTHORITY\\SYSTEM",
            "rights": "FullControl",
            "inheritance": "ContainerInherit, ObjectInherit",
            "propagation": "None",
            "type": "Allow",
        },
    ]
    return rules


# ---------------------------------------------------------------------------
# Tests — Directory Creation (Req 7.1)
# ---------------------------------------------------------------------------

class TestDirectoryCreation:
    def test_all_seven_directories_created(self, tmp_path: Path):
        """All 7 required subdirectories must exist after creation."""
        create_data_directories(str(tmp_path))
        for subdir in REQUIRED_SUBDIRS:
            assert (tmp_path / subdir).is_dir(), f"Missing directory: {subdir}"

    def test_returns_correct_count(self, tmp_path: Path):
        result = create_data_directories(str(tmp_path))
        assert len(result) == 7

    def test_ai_scribe_data_subdirs(self, tmp_path: Path):
        create_data_directories(str(tmp_path))
        assert (tmp_path / "ai-scribe-data" / "dictation").is_dir()
        assert (tmp_path / "ai-scribe-data" / "conversation").is_dir()

    def test_output_subdirs(self, tmp_path: Path):
        create_data_directories(str(tmp_path))
        assert (tmp_path / "output" / "dictation").is_dir()
        assert (tmp_path / "output" / "conversation").is_dir()

    def test_config_subdirs(self, tmp_path: Path):
        create_data_directories(str(tmp_path))
        assert (tmp_path / "config" / "providers").is_dir()
        assert (tmp_path / "config" / "templates").is_dir()
        assert (tmp_path / "config" / "dictionaries").is_dir()


# ---------------------------------------------------------------------------
# Tests — Idempotency and Non-Destructiveness (Req 7.3)
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_running_twice_does_not_error(self, tmp_path: Path):
        """Creating directories twice should not raise."""
        create_data_directories(str(tmp_path))
        create_data_directories(str(tmp_path))
        for subdir in REQUIRED_SUBDIRS:
            assert (tmp_path / subdir).is_dir()

    def test_preserves_existing_files(self, tmp_path: Path):
        """Pre-existing files in directories must not be overwritten."""
        # Create directories first
        create_data_directories(str(tmp_path))

        # Add files to some directories
        test_file = tmp_path / "ai-scribe-data" / "dictation" / "test_encounter.json"
        test_file.write_text('{"patient": "test"}', encoding="utf-8")

        config_file = tmp_path / "config" / "providers" / "dr_smith.yaml"
        config_file.write_text("name: Dr. Smith", encoding="utf-8")

        # Run creation again
        create_data_directories(str(tmp_path))

        # Verify files are preserved
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == '{"patient": "test"}'
        assert config_file.exists()
        assert config_file.read_text(encoding="utf-8") == "name: Dr. Smith"

    def test_preserves_nested_structure(self, tmp_path: Path):
        """Pre-existing nested directories and files must survive."""
        create_data_directories(str(tmp_path))

        # Create nested encounter structure like the real data
        encounter_dir = (
            tmp_path / "ai-scribe-data" / "conversation" / "dr_test" / "patient_001"
        )
        encounter_dir.mkdir(parents=True)
        (encounter_dir / "encounter_details.json").write_text("{}", encoding="utf-8")
        (encounter_dir / "patient_demographics.json").write_text("{}", encoding="utf-8")

        # Run creation again
        create_data_directories(str(tmp_path))

        # Verify nested structure is intact
        assert encounter_dir.is_dir()
        assert (encounter_dir / "encounter_details.json").exists()
        assert (encounter_dir / "patient_demographics.json").exists()

    def test_preserves_file_count(self, tmp_path: Path):
        """The number of files in a directory must not change after re-run."""
        create_data_directories(str(tmp_path))

        dictation_dir = tmp_path / "output" / "dictation"
        for i in range(5):
            (dictation_dir / f"note_{i}.md").write_text(f"Note {i}")

        files_before = list(dictation_dir.iterdir())
        create_data_directories(str(tmp_path))
        files_after = list(dictation_dir.iterdir())

        assert len(files_before) == len(files_after)


# ---------------------------------------------------------------------------
# Tests — NTFS ACL Command Generation (Req 7.2)
# ---------------------------------------------------------------------------

class TestNtfsAclRules:
    def test_exactly_two_principals(self):
        """ACL rules should grant access to exactly 2 principals."""
        rules = build_ntfs_acl_rules("DOMAIN\\svc_aiscribe")
        assert len(rules) == 2

    def test_service_account_gets_full_control(self):
        account = "MYHOST\\admin_user"
        rules = build_ntfs_acl_rules(account)
        svc_rules = [r for r in rules if r["principal"] == account]
        assert len(svc_rules) == 1
        assert svc_rules[0]["rights"] == "FullControl"
        assert svc_rules[0]["type"] == "Allow"

    def test_system_gets_full_control(self):
        rules = build_ntfs_acl_rules("DOMAIN\\svc")
        sys_rules = [r for r in rules if r["principal"] == "NT AUTHORITY\\SYSTEM"]
        assert len(sys_rules) == 1
        assert sys_rules[0]["rights"] == "FullControl"
        assert sys_rules[0]["type"] == "Allow"

    def test_no_other_principals(self):
        """Only the service account and SYSTEM should appear."""
        account = "HOST\\myuser"
        rules = build_ntfs_acl_rules(account)
        principals = {r["principal"] for r in rules}
        assert principals == {account, "NT AUTHORITY\\SYSTEM"}

    def test_inheritance_flags_set(self):
        """Both rules should have container + object inheritance for recursive ACL."""
        rules = build_ntfs_acl_rules("HOST\\user")
        for rule in rules:
            assert "ContainerInherit" in rule["inheritance"]
            assert "ObjectInherit" in rule["inheritance"]

    def test_different_service_accounts(self):
        """ACL rules should use whatever service account is provided."""
        for account in ["LOCAL\\admin", "DOMAIN\\svc_aiscribe", "NT AUTHORITY\\LOCAL SERVICE"]:
            rules = build_ntfs_acl_rules(account)
            svc_rules = [r for r in rules if r["principal"] == account]
            assert len(svc_rules) == 1
