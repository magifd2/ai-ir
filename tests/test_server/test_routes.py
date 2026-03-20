"""Tests for web UI routes using FastAPI TestClient."""
import json
import yaml
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from aiir.server.app import create_app, _format_steps, _strip_at

SAMPLE_REPORT = {
    "channel": "#test",
    "export_timestamp": "2026-03-19T10:00:00Z",
    "summary": {"title": "Test Incident", "severity": "high", "affected_systems": ["api-server"], "timeline": [], "root_cause": "OOM", "resolution": "restart", "summary": "Server went down."},
    "activity": {"incident_id": "#test", "channel": "#test", "participants": []},
    "roles": {"incident_id": "#test", "channel": "#test", "participants": [], "relationships": []},
    "tactics": [{"id": "tac-001", "title": "Check logs", "purpose": "find errors", "category": "log-analysis", "tools": ["grep"], "procedure": "grep error", "observations": "count errors", "tags": ["linux"], "source": {"channel": "#test", "participants": []}, "created_at": "2026-03-19"}],
}

SAMPLE_TACTIC = {
    "id": "tac-20260319-001",
    "title": "Test Tactic",
    "purpose": "testing",
    "category": "log-analysis",
    "tools": ["grep"],
    "procedure": "1. grep",
    "observations": "see output",
    "tags": ["linux", "logging"],
    "source": {"channel": "#test", "participants": ["alice"]},
    "created_at": "2026-03-19",
}

@pytest.fixture
def client(tmp_path):
    (tmp_path / "report.json").write_text(json.dumps(SAMPLE_REPORT))
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "tac-20260319-001-test.yaml").write_text(yaml.dump(SAMPLE_TACTIC))
    app = create_app(tmp_path)
    return TestClient(app)

def test_dashboard_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Test Incident" in resp.text

def test_dashboard_shows_tactic_count(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_report_view_returns_200(client):
    resp = client.get("/report?path=report.json")
    assert resp.status_code == 200
    assert "Test Incident" in resp.text

def test_report_view_404_for_missing(client):
    resp = client.get("/report?path=nonexistent.json")
    assert resp.status_code == 404

def test_knowledge_returns_200(client):
    resp = client.get("/knowledge")
    assert resp.status_code == 200
    assert "Test Tactic" in resp.text

def test_knowledge_filter_by_category(client):
    resp = client.get("/knowledge?category=log-analysis")
    assert resp.status_code == 200
    assert "Test Tactic" in resp.text

def test_knowledge_filter_no_match(client):
    resp = client.get("/knowledge?category=nonexistent")
    assert resp.status_code == 200
    assert "Test Tactic" not in resp.text

def test_tactic_view_returns_200(client):
    resp = client.get("/tactic?path=knowledge/tac-20260319-001-test.yaml")
    assert resp.status_code == 200
    assert "Test Tactic" in resp.text

def test_tactic_view_404_for_missing(client):
    resp = client.get("/tactic?path=knowledge/nonexistent.yaml")
    assert resp.status_code == 404

def test_api_reports_json(client):
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Incident"

def test_api_knowledge_json(client):
    resp = client.get("/api/knowledge")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "tac-20260319-001"

def test_path_traversal_rejected(client):
    resp = client.get("/report?path=../../etc/passwd")
    assert resp.status_code == 404


# --- _format_steps filter tests ---

@pytest.mark.parametrize("text,expected", [
    ("", ""),
    ("1. Only one step.", "1. Only one step."),
    (
        "1. First step. 2. Second step. 3. Third step.",
        "1. First step.\n2. Second step.\n3. Third step.",
    ),
    (
        "1. Step one. 2. Step two.",
        "1. Step one.\n2. Step two.",
    ),
    (
        "Already\nhas\nnewlines",
        "Already\nhas\nnewlines",
    ),
])
def test_format_steps(text, expected):
    assert _format_steps(text) == expected


# --- _strip_at filter tests ---

@pytest.mark.parametrize("name,expected", [
    ("alice", "alice"),        # no @ → unchanged
    ("@wave", "wave"),         # LLM-added @ → stripped
    ("@@double", "double"),    # edge case: multiple @ → all stripped
    ("", ""),                  # empty string
])
def test_strip_at(name, expected):
    assert _strip_at(name) == expected


SAMPLE_REVIEW = {
    "incident_id": "abc123",
    "channel": "#test",
    "overall_score": "good",
    "phases": [{"phase": "detection", "estimated_duration": "5m", "quality": "good", "notes": ""}],
    "communication": {"overall": "good", "delays_observed": [], "silos_observed": []},
    "role_clarity": {"ic_identified": True, "ic_name": "alice", "gaps": [], "overlaps": []},
    "tool_appropriateness": "good",
    "strengths": ["Quick response"],
    "improvements": ["Better runbook"],
    "checklist": [{"item": "Check alerts", "priority": "high"}],
}


def test_report_view_shows_review_tab_when_present(tmp_path):
    """対応評価タブは review JSON が存在するときのみ表示される。"""
    import json as _json
    (tmp_path / "report.json").write_text(_json.dumps(SAMPLE_REPORT))
    (tmp_path / "report.review.json").write_text(_json.dumps(SAMPLE_REVIEW))
    app = create_app(tmp_path)
    from fastapi.testclient import TestClient
    c = TestClient(app)
    resp = c.get("/report?path=report.json")
    assert resp.status_code == 200
    assert "対応評価" in resp.text
    assert "Quick response" in resp.text


def test_report_view_hides_review_tab_when_absent(client):
    """review JSON がない場合、対応評価タブは表示されない。"""
    resp = client.get("/report?path=report.json")
    assert resp.status_code == 200
    assert "対応評価" not in resp.text


def test_report_view_no_double_at_for_bot(tmp_path):
    """Bot usernames starting with '@' must not render as '@@' in the report view."""
    report = dict(SAMPLE_REPORT)
    report["activity"] = {
        "incident_id": "#test",
        "channel": "#test",
        "participants": [
            {
                "user_name": "@bot-account",   # LLM returned '@'-prefixed name
                "role_hint": "Bot",
                "actions": [],
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(__import__("json").dumps(report))
    app = create_app(tmp_path)
    from fastapi.testclient import TestClient
    c = TestClient(app)
    resp = c.get(f"/report?path={path}")
    assert resp.status_code == 200
    assert "@@bot-account" not in resp.text
    assert "@bot-account" in resp.text
