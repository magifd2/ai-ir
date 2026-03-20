"""Tests for the translate module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aiir.translate.translator import (
    SUPPORTED_LANGS,
    _lang_name,
    _translate_summary,
    _translate_activity,
    _translate_roles,
    _translate_tactics,
    translate_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPORT = {
    "channel": "#incident-2026",
    "summary": {
        "title": "Database outage",
        "severity": "high",
        "affected_systems": ["db-primary"],
        "timeline": [
            {"timestamp": "2026-03-20T10:00:00Z", "actor": "alice", "event": "Alert fired"}
        ],
        "root_cause": "OOM killer terminated postgres",
        "resolution": "Restarted with increased memory limit",
        "summary": "The primary database was killed by OOM.",
    },
    "activity": {
        "incident_id": "#incident-2026",
        "channel": "#incident-2026",
        "participants": [
            {
                "user_name": "alice",
                "role_hint": "Lead Responder",
                "actions": [
                    {
                        "timestamp": "2026-03-20T10:05:00Z",
                        "purpose": "Check memory usage",
                        "method": "free -m",
                        "findings": "Memory was exhausted",
                    }
                ],
            }
        ],
    },
    "roles": {
        "incident_id": "#incident-2026",
        "channel": "#incident-2026",
        "participants": [
            {
                "user_name": "alice",
                "inferred_role": "Lead Responder",
                "confidence": "high",
                "evidence": ["alice ran diagnostics"],
            }
        ],
        "relationships": [
            {
                "from_user": "alice",
                "to_user": "bob",
                "relationship_type": "reports_to",
                "description": "alice escalated to bob",
            }
        ],
    },
    "tactics": [
        {
            "id": "tac-20260320-001",
            "title": "Check OOM killer logs",
            "purpose": "Identify which process was killed",
            "category": "linux-kernel",
            "tools": ["dmesg", "journalctl"],
            "procedure": "1. Run dmesg. 2. Filter OOM lines.",
            "observations": "Look for 'Out of memory' lines.",
            "tags": ["linux", "oom"],
            "source": {"channel": "#incident-2026", "participants": ["alice"]},
            "created_at": "2026-03-20",
        }
    ],
}


def _make_mock_client(return_data: dict) -> MagicMock:
    """Return a mock LLMClient whose complete_json always returns the given dict as JSON."""
    client = MagicMock()
    client.complete_json.return_value = json.dumps(return_data, ensure_ascii=False)
    return client


# ---------------------------------------------------------------------------
# _lang_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code,expected", [
    ("ja", "Japanese"),
    ("zh", "Simplified Chinese"),
    ("de", "German"),
    ("xx", "xx"),  # unknown code → passthrough
])
def test_lang_name(code, expected):
    assert _lang_name(code) == expected


def test_supported_langs_not_empty():
    assert len(SUPPORTED_LANGS) >= 5


# ---------------------------------------------------------------------------
# _translate_summary
# ---------------------------------------------------------------------------


def test_translate_summary_updates_narrative_fields():
    translated_payload = {
        "title": "データベース障害",
        "root_cause": "OOMキラーがpostgresを終了させた",
        "resolution": "メモリ制限を増やして再起動した",
        "summary": "プライマリデータベースがOOMにより停止した。",
        "timeline": [{"timestamp": "2026-03-20T10:00:00Z", "actor": "alice", "event": "アラート発火"}],
    }
    client = _make_mock_client(translated_payload)
    result = _translate_summary(SAMPLE_REPORT["summary"], "ja", client)

    assert result["title"] == "データベース障害"
    assert result["root_cause"] == "OOMキラーがpostgresを終了させた"
    assert result["timeline"][0]["event"] == "アラート発火"
    # Non-narrative fields unchanged
    assert result["severity"] == "high"
    assert result["affected_systems"] == ["db-primary"]


def test_translate_summary_preserves_on_missing_key():
    """If LLM omits a key, the original value is kept."""
    client = _make_mock_client({"title": "タイトル"})  # missing other keys
    result = _translate_summary(SAMPLE_REPORT["summary"], "ja", client)
    assert result["root_cause"] == "OOM killer terminated postgres"


# ---------------------------------------------------------------------------
# _translate_activity
# ---------------------------------------------------------------------------


def test_translate_activity_updates_narrative_fields():
    translated_payload = {
        "participants": [
            {
                "user_name": "alice",
                "role_hint": "主担当者",
                "actions": [
                    {
                        "timestamp": "2026-03-20T10:05:00Z",
                        "purpose": "メモリ使用量を確認する",
                        "findings": "メモリが枯渇していた",
                    }
                ],
            }
        ]
    }
    client = _make_mock_client(translated_payload)
    result = _translate_activity(SAMPLE_REPORT["activity"], "ja", client)

    assert result["participants"][0]["role_hint"] == "主担当者"
    assert result["participants"][0]["actions"][0]["purpose"] == "メモリ使用量を確認する"
    # method (technical) is NOT in payload — verify original preserved
    assert result["participants"][0]["actions"][0]["method"] == "free -m"
    # Non-narrative fields unchanged
    assert result["channel"] == "#incident-2026"


# ---------------------------------------------------------------------------
# _translate_roles
# ---------------------------------------------------------------------------


def test_translate_roles_updates_narrative_fields():
    translated_payload = {
        "participants": [
            {
                "user_name": "alice",
                "inferred_role": "主担当者",
                "evidence": ["aliceが診断を実施した"],
            }
        ],
        "relationships": [
            {
                "from_user": "alice",
                "to_user": "bob",
                "description": "aliceがbobにエスカレーションした",
            }
        ],
    }
    client = _make_mock_client(translated_payload)
    result = _translate_roles(SAMPLE_REPORT["roles"], "ja", client)

    assert result["participants"][0]["inferred_role"] == "主担当者"
    assert result["relationships"][0]["description"] == "aliceがbobにエスカレーションした"
    # relationship_type preserved
    assert result["relationships"][0]["relationship_type"] == "reports_to"
    assert result["channel"] == "#incident-2026"


# ---------------------------------------------------------------------------
# _translate_tactics
# ---------------------------------------------------------------------------


def test_translate_tactics_updates_narrative_fields():
    translated_payload = {
        "tactics": [
            {
                "title": "OOMキラーログを確認する",
                "purpose": "どのプロセスが終了させられたかを特定する",
                "procedure": "1. dmesgを実行する。 2. OOM行をフィルタリングする。",
                "observations": "「Out of memory」行を探す。",
            }
        ]
    }
    client = _make_mock_client(translated_payload)
    result = _translate_tactics(SAMPLE_REPORT["tactics"], "ja", client)

    assert result[0]["title"] == "OOMキラーログを確認する"
    assert result[0]["purpose"] == "どのプロセスが終了させられたかを特定する"
    # Technical fields preserved
    assert result[0]["id"] == "tac-20260320-001"
    assert result[0]["tools"] == ["dmesg", "journalctl"]
    assert result[0]["tags"] == ["linux", "oom"]
    assert result[0]["category"] == "linux-kernel"
    assert result[0]["created_at"] == "2026-03-20"


# ---------------------------------------------------------------------------
# translate_report (end-to-end)
# ---------------------------------------------------------------------------


def test_translate_report_adds_lang_field():
    client = MagicMock()
    # Return minimal valid JSON for each section call
    client.complete_json.side_effect = [
        json.dumps({"title": "T", "root_cause": "R", "resolution": "Re", "summary": "S", "timeline": [{"timestamp": "", "actor": "alice", "event": "E"}]}),
        json.dumps({"participants": [{"user_name": "alice", "role_hint": "L", "actions": [{"timestamp": "", "purpose": "P", "findings": "F"}]}]}),
        json.dumps({"participants": [{"user_name": "alice", "inferred_role": "L", "evidence": []}], "relationships": [{"from_user": "alice", "to_user": "bob", "description": "D"}]}),
        json.dumps({"tactics": [{"title": "T", "purpose": "P", "procedure": "Pr", "observations": "O"}]}),
    ]
    result = translate_report(SAMPLE_REPORT, "ja", client)
    assert result["lang"] == "ja"
    assert client.complete_json.call_count == 4


def test_translate_report_skips_missing_sections():
    partial = {"summary": SAMPLE_REPORT["summary"], "tactics": SAMPLE_REPORT["tactics"]}
    client = MagicMock()
    client.complete_json.side_effect = [
        json.dumps({"title": "T", "root_cause": "R", "resolution": "Re", "summary": "S", "timeline": []}),
        json.dumps({"tactics": [{"title": "T", "purpose": "P", "procedure": "Pr", "observations": "O"}]}),
    ]
    result = translate_report(partial, "ja", client)
    # Only 2 calls (summary + tactics); activity/roles absent
    assert client.complete_json.call_count == 2
    assert "activity" not in result
