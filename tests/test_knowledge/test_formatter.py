"""Tests for aiir.knowledge.formatter module."""

import yaml
import pytest

from aiir.models import Tactic, TacticSource
from aiir.knowledge.formatter import save_tactics, tactic_to_yaml


def _make_tactic(**kwargs) -> Tactic:
    """Helper to create a Tactic with defaults."""
    defaults = dict(
        id="tac-001",
        title="Log grep analysis",
        purpose="Find error patterns",
        category="log-analysis",
        tools=["grep", "awk"],
        procedure="1. Access logs\n2. Run grep",
        observations="Error counts indicate severity",
        tags=["linux", "logging"],
        source=TacticSource(channel="#ir", participants=["alice", "bob"]),
        created_at="2026-03-19",
    )
    defaults.update(kwargs)
    return Tactic(**defaults)


# ---------------------------------------------------------------------------
# tactic_to_yaml
# ---------------------------------------------------------------------------


def test_tactic_to_yaml_returns_string():
    """Test that tactic_to_yaml returns a string."""
    tactic = _make_tactic()
    result = tactic_to_yaml(tactic)
    assert isinstance(result, str)


def test_tactic_to_yaml_valid_yaml():
    """Test that tactic_to_yaml output is valid YAML."""
    tactic = _make_tactic()
    yaml_str = tactic_to_yaml(tactic)
    # Should not raise
    data = yaml.safe_load(yaml_str)
    assert data is not None


def test_tactic_to_yaml_id():
    """Test that tactic ID is preserved in YAML output."""
    tactic = _make_tactic(id="tac-20260319-001")
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["id"] == "tac-20260319-001"


def test_tactic_to_yaml_category():
    """Test that category is preserved in YAML output."""
    tactic = _make_tactic(category="log-analysis")
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["category"] == "log-analysis"


def test_tactic_to_yaml_tools():
    """Test that tools list is preserved in YAML output."""
    tactic = _make_tactic(tools=["grep", "awk"])
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert "grep" in data["tools"]
    assert "awk" in data["tools"]


def test_tactic_to_yaml_source():
    """Test that source metadata is preserved in YAML output."""
    tactic = _make_tactic(
        source=TacticSource(channel="#ir", participants=["alice", "bob"])
    )
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["source"]["channel"] == "#ir"
    assert "alice" in data["source"]["participants"]
    assert "bob" in data["source"]["participants"]


def test_tactic_to_yaml_created_at():
    """Test that created_at is preserved in YAML output."""
    tactic = _make_tactic(created_at="2026-03-19")
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["created_at"] == "2026-03-19"


def test_tactic_to_yaml_tags():
    """Test that tags list is preserved in YAML output."""
    tactic = _make_tactic(tags=["linux", "logging", "grep"])
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert "linux" in data["tags"]
    assert "logging" in data["tags"]


def test_tactic_to_yaml_key_order():
    """Test that YAML output starts with 'id' (sort_keys=False)."""
    tactic = _make_tactic()
    yaml_str = tactic_to_yaml(tactic)
    # First non-empty line should be the 'id' key
    first_key_line = next(
        line for line in yaml_str.splitlines() if line.strip() and not line.startswith("#")
    )
    assert first_key_line.startswith("id:")


def test_tactic_to_yaml_confidence_default():
    """Confidence defaults to 'inferred' and appears in YAML."""
    tactic = _make_tactic()
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["confidence"] == "inferred"


def test_tactic_to_yaml_confidence_confirmed():
    """Confirmed confidence is preserved in YAML."""
    tactic = _make_tactic(confidence="confirmed", evidence="alice pasted grep output at 10:15")
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["confidence"] == "confirmed"
    assert data["evidence"] == "alice pasted grep output at 10:15"


def test_tactic_to_yaml_confidence_suggested():
    """Suggested confidence is preserved in YAML."""
    tactic = _make_tactic(confidence="suggested", evidence="bob proposed this as a next step")
    data = yaml.safe_load(tactic_to_yaml(tactic))
    assert data["confidence"] == "suggested"


# ---------------------------------------------------------------------------
# save_tactics
# ---------------------------------------------------------------------------


def test_save_tactics_creates_files(tmp_path):
    """Test that save_tactics creates YAML files."""
    tactics = [_make_tactic(id="tac-001", title="Test Tactic")]
    saved = save_tactics(tactics, tmp_path / "knowledge")
    assert len(saved) == 1
    assert saved[0].exists()


def test_save_tactics_creates_directory(tmp_path):
    """Test that save_tactics creates the output directory if needed."""
    output_dir = tmp_path / "new" / "nested" / "dir"
    assert not output_dir.exists()
    tactics = [_make_tactic()]
    save_tactics(tactics, output_dir)
    assert output_dir.exists()


def test_save_tactics_file_content(tmp_path):
    """Test that saved files contain valid YAML with correct content."""
    tactic = _make_tactic(id="tac-20260319-001", title="Check Pod Logs")
    saved = save_tactics([tactic], tmp_path / "knowledge")
    content = saved[0].read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert data["id"] == "tac-20260319-001"
    assert data["title"] == "Check Pod Logs"


def test_save_tactics_filename_format(tmp_path):
    """Test that saved files follow the naming convention."""
    tactic = _make_tactic(id="tac-20260319-001", title="Check Pod Logs For OOM")
    saved = save_tactics([tactic], tmp_path / "knowledge")
    filename = saved[0].name
    assert filename.startswith("tac-20260319-001-")
    assert filename.endswith(".yaml")


def test_save_tactics_multiple(tmp_path):
    """Test saving multiple tactics."""
    tactics = [
        _make_tactic(id=f"tac-00{i}", title=f"Tactic {i}")
        for i in range(1, 4)
    ]
    saved = save_tactics(tactics, tmp_path / "knowledge")
    assert len(saved) == 3
    assert all(p.exists() for p in saved)


def test_save_tactics_empty_list(tmp_path):
    """Test that saving an empty list returns an empty list."""
    saved = save_tactics([], tmp_path / "knowledge")
    assert saved == []


def test_save_tactics_unicode_content(tmp_path):
    """Test that Unicode content is preserved in YAML files."""
    tactic = _make_tactic(
        purpose="Find errors in Japanese log files: エラーを探す",
        tags=["japanese", "unicode"],
    )
    saved = save_tactics([tactic], tmp_path / "knowledge")
    content = saved[0].read_text(encoding="utf-8")
    assert "エラーを探す" in content
