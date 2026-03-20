"""Tests for incident response process reviewer."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from aiir.analyze.reviewer import (
    _build_system_prompt,
    _format_report_for_review,
    review_incident,
)
from aiir.models import IncidentReview

SAMPLE_REPORT = {
    "incident_id": "abc123def456",
    "channel": "#incident-2026",
    "metadata": {"channel": "#incident-2026", "generated_at": "2026-03-19T10:00:00Z"},
    "summary": {
        "title": "Test Incident",
        "severity": "high",
        "affected_systems": ["api-server"],
        "timeline": [{"timestamp": "09:00", "actor": "alice", "event": "alert triggered"}],
        "root_cause": "OOM",
        "resolution": "restarted pod",
        "summary": "Server went down due to OOM.",
    },
    "activity": {"incident_id": "#incident-2026", "channel": "#incident-2026", "participants": []},
    "roles": {"incident_id": "#incident-2026", "channel": "#incident-2026", "participants": [], "relationships": []},
    "tactics": [],
}

SAMPLE_REVIEW_JSON = json.dumps({
    "incident_id": "abc123def456",
    "channel": "#incident-2026",
    "overall_score": "good",
    "phases": [
        {"phase": "detection", "estimated_duration": "~5 minutes", "quality": "good", "notes": "Fast alert."},
        {"phase": "resolution", "estimated_duration": "~30 minutes", "quality": "adequate", "notes": "Pod restart."},
    ],
    "communication": {
        "overall": "Generally good.",
        "delays_observed": [],
        "silos_observed": [],
    },
    "role_clarity": {
        "ic_identified": True,
        "ic_name": "alice",
        "gaps": [],
        "overlaps": [],
    },
    "tool_appropriateness": "Appropriate tools were used.",
    "strengths": ["Quick detection", "Clear communication"],
    "improvements": ["Add runbook link in channel topic"],
    "checklist": [
        {"item": "Verify alert thresholds quarterly", "priority": "medium"},
    ],
})


# ---------------------------------------------------------------------------
# System prompt checks
# ---------------------------------------------------------------------------

def test_system_prompt_requires_json():
    assert "JSON" in _build_system_prompt()


def test_system_prompt_no_nonce_tag():
    """reviewer.py does not pass user message text, so no nonce tag should appear."""
    prompt = _build_system_prompt()
    assert "<user_message_" not in prompt


def test_system_prompt_mentions_key_dimensions():
    prompt = _build_system_prompt()
    for keyword in ("communication", "role", "checklist", "overall_score"):
        assert keyword in prompt, f"'{keyword}' missing from system prompt"


def test_system_prompt_mentions_phases():
    prompt = _build_system_prompt()
    for phase in ("detection", "containment", "resolution"):
        assert phase in prompt


def test_system_prompt_explains_confidence_levels():
    """Reviewer must know the 3 confidence levels and how to treat each."""
    prompt = _build_system_prompt()
    for level in ("confirmed", "inferred", "suggested"):
        assert level in prompt, f"confidence level '{level}' missing from reviewer prompt"


def test_system_prompt_warns_against_evaluating_suggested_as_used():
    """Reviewer must not treat suggested-only tactics as having been executed."""
    prompt = _build_system_prompt()
    # The prompt should explicitly say suggested tactics were not used
    assert "suggested" in prompt
    # The instruction to base evaluation only on confirmed tactics must be present
    assert "confirmed" in prompt


# ---------------------------------------------------------------------------
# _format_report_for_review
# ---------------------------------------------------------------------------

def test_format_excludes_raw_messages():
    """Raw Slack message text must not be re-sent to the LLM."""
    result = _format_report_for_review(SAMPLE_REPORT)
    assert "messages" not in json.loads(result)


def test_format_includes_summary():
    result = json.loads(_format_report_for_review(SAMPLE_REPORT))
    assert "summary" in result


def test_format_includes_tactics():
    result = json.loads(_format_report_for_review(SAMPLE_REPORT))
    assert "tactics" in result


def test_format_includes_channel():
    result = json.loads(_format_report_for_review(SAMPLE_REPORT))
    assert result["channel"] == "#incident-2026"


# ---------------------------------------------------------------------------
# review_incident
# ---------------------------------------------------------------------------

def _make_client(response: str) -> MagicMock:
    client = MagicMock()
    client.complete_json.return_value = response
    return client


def test_review_incident_returns_model():
    client = _make_client(SAMPLE_REVIEW_JSON)
    result = review_incident(SAMPLE_REPORT, client)
    assert isinstance(result, IncidentReview)
    assert result.overall_score == "good"
    assert len(result.phases) == 2
    assert result.role_clarity.ic_name == "alice"


def test_review_incident_invalid_json_raises():
    client = _make_client("not json at all {{{")
    with pytest.raises(ValueError, match="invalid JSON"):
        review_incident(SAMPLE_REPORT, client)


def test_review_incident_fills_missing_incident_id():
    """If the LLM omits incident_id, it should be filled from the report."""
    data = json.loads(SAMPLE_REVIEW_JSON)
    del data["incident_id"]
    client = _make_client(json.dumps(data))
    result = review_incident(SAMPLE_REPORT, client)
    assert result.incident_id == "abc123def456"


def test_review_incident_fills_missing_channel():
    data = json.loads(SAMPLE_REVIEW_JSON)
    del data["channel"]
    client = _make_client(json.dumps(data))
    result = review_incident(SAMPLE_REPORT, client)
    assert result.channel == "#incident-2026"
