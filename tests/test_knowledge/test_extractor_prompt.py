"""Tests for extractor system prompt category coverage.

Verifies that platform-specific knowledge categories are present in the
prompt so the LLM can correctly classify tactics from Windows, Linux,
and macOS incident conversations.

The system prompt is built dynamically via ``_build_system_prompt(nonce)``
to embed the sanitization nonce in data boundary tags.
"""

from __future__ import annotations

import pytest
from aiir.knowledge.extractor import _build_system_prompt

# Use a fixed test nonce so assertions are deterministic
_TEST_NONCE = "test1234abcd5678"
SYSTEM_PROMPT = _build_system_prompt(_TEST_NONCE)


# ---------------------------------------------------------------------------
# Cross-platform categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", [
    "log-analysis",
    "network-analysis",
    "process-analysis",
    "memory-forensics",
    "database-analysis",
    "container-analysis",
    "cloud-analysis",
    "malware-analysis",
    "authentication-analysis",
])
def test_cross_platform_category_present(category):
    assert category in SYSTEM_PROMPT, f"Cross-platform category '{category}' missing from SYSTEM_PROMPT"


# ---------------------------------------------------------------------------
# Linux-specific categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", [
    "linux-systemd",
    "linux-auditd",
    "linux-procfs",
    "linux-ebpf",
    "linux-kernel",
])
def test_linux_category_present(category):
    assert category in SYSTEM_PROMPT, f"Linux category '{category}' missing from SYSTEM_PROMPT"


@pytest.mark.parametrize("tool", [
    "journalctl",
    "ausearch",
    "aureport",
    "/proc/",
    "execsnoop",
    "bpftool",
    "dmesg",
    "lsmod",
])
def test_linux_tool_mentioned(tool):
    assert tool in SYSTEM_PROMPT, f"Linux tool '{tool}' not mentioned in SYSTEM_PROMPT"


# ---------------------------------------------------------------------------
# Windows-specific categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", [
    "windows-event-log",
    "windows-registry",
    "windows-powershell",
    "windows-active-directory",
    "windows-filesystem",
    "windows-defender",
])
def test_windows_category_present(category):
    assert category in SYSTEM_PROMPT, f"Windows category '{category}' missing from SYSTEM_PROMPT"


@pytest.mark.parametrize("tool_or_concept", [
    "wevtutil",
    "Get-WinEvent",
    "Sysmon",
    "reg query",
    "Autoruns",
    "Script Block",
    "Get-ADUser",
    "vssadmin",
    "MpCmdRun",
])
def test_windows_tool_mentioned(tool_or_concept):
    assert tool_or_concept in SYSTEM_PROMPT, (
        f"Windows tool/concept '{tool_or_concept}' not mentioned in SYSTEM_PROMPT"
    )


# ---------------------------------------------------------------------------
# macOS-specific categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", [
    "macos-unified-logging",
    "macos-launchd",
    "macos-gatekeeper",
    "macos-endpoint-security",
    "macos-filesystem",
])
def test_macos_category_present(category):
    assert category in SYSTEM_PROMPT, f"macOS category '{category}' missing from SYSTEM_PROMPT"


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def test_other_category_present():
    assert "other" in SYSTEM_PROMPT


def test_prompt_mentions_tactic_definition():
    assert "tactic" in SYSTEM_PROMPT.lower()


def test_prompt_requires_json_response():
    assert "JSON" in SYSTEM_PROMPT


def test_prompt_has_nonce_tagged_injection_guard():
    """The data boundary tag must include the nonce, not a plain tag name."""
    assert f"<user_message_{_TEST_NONCE}>" in SYSTEM_PROMPT


def test_prompt_nonce_tag_differs_per_call():
    """Different nonces produce different tag names in the prompt."""
    prompt_a = _build_system_prompt("nonce_aaa")
    prompt_b = _build_system_prompt("nonce_bbb")
    assert "<user_message_nonce_aaa>" in prompt_a
    assert "<user_message_nonce_bbb>" in prompt_b
    assert "<user_message_nonce_aaa>" not in prompt_b


# ---------------------------------------------------------------------------
# Confidence classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["confirmed", "inferred", "suggested"])
def test_confidence_levels_present_in_prompt(level):
    """All three confidence levels must be defined in the prompt."""
    assert level in SYSTEM_PROMPT, f"Confidence level '{level}' missing from SYSTEM_PROMPT"


def test_prompt_explains_confirmed_criteria():
    """Prompt must explain what makes a tactic 'confirmed'."""
    # Evidence of actual execution (output shared) must be described
    assert "output" in SYSTEM_PROMPT.lower()


def test_prompt_includes_confidence_in_json_schema():
    """The JSON schema example must include the confidence field."""
    assert '"confidence"' in SYSTEM_PROMPT


def test_prompt_includes_evidence_in_json_schema():
    """The JSON schema example must include the evidence field."""
    assert '"evidence"' in SYSTEM_PROMPT
