"""Tests for server data loader."""
import json
import yaml
import pytest
from pathlib import Path
from aiir.server.loader import scan_reports, scan_tactics, load_report, load_tactic, load_report_by_id, load_review

SAMPLE_REPORT = {
    "channel": "#test",
    "export_timestamp": "2026-03-19T10:00:00Z",
    "summary": {"title": "Test Incident", "severity": "high", "affected_systems": [], "timeline": [], "root_cause": "", "resolution": "", "summary": "test"},
    "activity": {"incident_id": "#test", "channel": "#test", "participants": []},
    "roles": {"incident_id": "#test", "channel": "#test", "participants": [], "relationships": []},
    "tactics": [],
}

SAMPLE_TACTIC = {
    "id": "tac-20260319-001",
    "title": "Test Tactic",
    "purpose": "testing",
    "category": "log-analysis",
    "tools": ["grep"],
    "procedure": "1. do thing",
    "observations": "see result",
    "tags": ["test"],
    "source": {"channel": "#test", "participants": ["alice"]},
    "created_at": "2026-03-19",
}

@pytest.fixture
def data_dir(tmp_path):
    # Write sample report
    (tmp_path / "report.json").write_text(json.dumps(SAMPLE_REPORT))
    # Write a non-report JSON (should be ignored)
    (tmp_path / "other.json").write_text('{"foo": "bar"}')
    # Write sample tactic
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "tac-20260319-001-test.yaml").write_text(yaml.dump(SAMPLE_TACTIC))
    return tmp_path

def test_scan_reports_finds_report(data_dir):
    reports = scan_reports(data_dir)
    assert len(reports) == 1
    assert reports[0]["summary"]["title"] == "Test Incident"

def test_scan_reports_ignores_non_reports(data_dir):
    reports = scan_reports(data_dir)
    assert all("summary" in r and "tactics" in r for r in reports)

def test_scan_tactics_finds_tactic(data_dir):
    tactics = scan_tactics(data_dir)
    assert len(tactics) == 1
    assert tactics[0]["id"] == "tac-20260319-001"

def test_load_report_success(data_dir):
    report = load_report(data_dir, "report.json")
    assert report is not None
    assert report["summary"]["title"] == "Test Incident"

def test_load_report_path_traversal(data_dir, tmp_path):
    # Attempt path traversal
    result = load_report(data_dir, "../../etc/passwd")
    assert result is None

def test_load_tactic_success(data_dir):
    tactic = load_tactic(data_dir, "knowledge/tac-20260319-001-test.yaml")
    assert tactic is not None
    assert tactic["id"] == "tac-20260319-001"

def test_load_tactic_path_traversal(data_dir):
    result = load_tactic(data_dir, "../../etc/shadow")
    assert result is None

def test_scan_reports_adds_metadata(data_dir):
    reports = scan_reports(data_dir)
    assert "_filename" in reports[0]
    assert "_path" in reports[0]

def test_scan_tactics_adds_metadata(data_dir):
    tactics = scan_tactics(data_dir)
    assert "_filename" in tactics[0]
    assert "_path" in tactics[0]


def test_scan_reports_groups_by_incident_id(tmp_path):
    """Two reports with the same incident_id are merged into one entry with _langs."""
    base = {
        "incident_id": "abc123def456",
        "summary": {"title": "T", "severity": "high", "affected_systems": [], "timeline": [], "root_cause": "", "resolution": "", "summary": "s"},
        "tactics": [],
    }
    en = dict(base, lang="en")
    ja = dict(base, lang="ja", summary=dict(base["summary"], title="日本語タイトル"))
    (tmp_path / "report.json").write_text(json.dumps(en))
    (tmp_path / "report.ja.json").write_text(json.dumps(ja))

    reports = scan_reports(tmp_path)
    assert len(reports) == 1
    r = reports[0]
    assert set(r["_langs"].keys()) == {"en", "ja"}


def test_load_report_by_id_returns_requested_lang(tmp_path):
    base = {
        "incident_id": "aabbccddeeff",
        "summary": {"title": "T", "severity": "low", "affected_systems": [], "timeline": [], "root_cause": "", "resolution": "", "summary": "s"},
        "tactics": [],
    }
    en = dict(base, lang="en")
    ja = dict(base, lang="ja")
    (tmp_path / "report.json").write_text(json.dumps(en))
    (tmp_path / "report.ja.json").write_text(json.dumps(ja))

    result = load_report_by_id(tmp_path, "aabbccddeeff", lang="ja")
    assert result is not None
    assert result.get("lang") == "ja"


def test_load_report_by_id_falls_back_to_en(tmp_path):
    base = {
        "incident_id": "112233445566",
        "summary": {"title": "T", "severity": "low", "affected_systems": [], "timeline": [], "root_cause": "", "resolution": "", "summary": "s"},
        "tactics": [],
    }
    (tmp_path / "report.json").write_text(json.dumps(dict(base, lang="en")))

    result = load_report_by_id(tmp_path, "112233445566", lang="ja")
    assert result is not None
    assert result.get("lang") == "en"  # fallback


def test_load_report_by_id_unknown_id(tmp_path):
    assert load_report_by_id(tmp_path, "nonexistent000", lang="en") is None


SAMPLE_REVIEW = {
    "incident_id": "abc123",
    "channel": "#test",
    "overall_score": "good",
    "phases": [{"phase": "detection", "estimated_duration": "5m", "quality": "good", "notes": ""}],
    "communication": {"overall": "good", "delays_observed": [], "silos_observed": []},
    "role_clarity": {"ic_identified": True, "ic_name": "alice", "gaps": [], "overlaps": []},
    "tool_appropriateness": "good",
    "strengths": [],
    "improvements": [],
    "checklist": [],
}

import json as _json

def test_load_review_returns_data(tmp_path):
    (tmp_path / "report.json").write_text(_json.dumps(SAMPLE_REPORT))
    (tmp_path / "report.review.json").write_text(_json.dumps(SAMPLE_REVIEW))
    result = load_review(tmp_path, "report.json")
    assert result is not None
    assert result["overall_score"] == "good"


def test_load_review_returns_none_when_missing(tmp_path):
    (tmp_path / "report.json").write_text(_json.dumps(SAMPLE_REPORT))
    assert load_review(tmp_path, "report.json") is None


def test_load_review_ignores_invalid_json(tmp_path):
    (tmp_path / "report.json").write_text(_json.dumps(SAMPLE_REPORT))
    (tmp_path / "report.review.json").write_text("not json {{{")
    assert load_review(tmp_path, "report.json") is None


def test_load_review_strips_lang_suffix(tmp_path):
    """report.ja.json should resolve to report.review.json."""
    (tmp_path / "report.ja.json").write_text(_json.dumps(SAMPLE_REPORT))
    (tmp_path / "report.review.json").write_text(_json.dumps(SAMPLE_REVIEW))
    result = load_review(tmp_path, "report.ja.json")
    assert result is not None


def test_load_review_path_traversal(tmp_path):
    assert load_review(tmp_path, "../../etc/passwd.json") is None
