"""Scan directories and load ai-ir output files."""
from pathlib import Path
import json
import yaml


def scan_reports(data_dir: Path) -> list[dict]:
    """Find, load, and group all report JSON files in data_dir (recursive).

    Reports sharing the same ``incident_id`` are recognised as language variants
    of the same incident and merged into a single entry.  The canonical (English)
    version is used as the base; all other language paths are stored in
    ``_langs`` as a ``{lang_code: rel_path}`` mapping.

    Reports without an ``incident_id`` (pre-v0.4.0 files) are each treated as a
    standalone entry, keyed by their file path.
    """
    # First pass: collect all valid report files
    raw: list[dict] = []
    for path in sorted(data_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "summary" in data and "tactics" in data:
                data["_filename"] = path.name
                data["_path"] = str(path.relative_to(data_dir))
                raw.append(data)
        except Exception:
            continue

    # Second pass: group by incident_id
    groups: dict[str, dict] = {}   # incident_id → canonical report dict
    no_id: list[dict] = []

    for r in raw:
        iid = r.get("incident_id")
        if not iid:
            no_id.append(r)
            continue
        lang = r.get("lang", "en")
        if iid not in groups:
            # First variant seen — use as base regardless of language
            groups[iid] = r
            groups[iid].setdefault("_langs", {})[lang] = r["_path"]
        else:
            # Merge additional language variant
            existing = groups[iid]
            existing.setdefault("_langs", {})[lang] = r["_path"]
            # Prefer the English version as the canonical display copy
            if lang == "en" and existing.get("lang") != "en":
                rel_path = existing["_path"]
                filename = existing["_filename"]
                langs = existing["_langs"]
                groups[iid] = dict(r)
                groups[iid]["_langs"] = langs
                groups[iid]["_path"] = r["_path"]
                groups[iid]["_filename"] = r["_filename"]

    result = list(groups.values()) + no_id
    return result


def scan_tactics(data_dir: Path) -> list[dict]:
    """Find and load all tactic YAML files in data_dir (recursive)."""
    tactics = []
    for path in sorted(data_dir.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("id", "")).startswith("tac-"):
                data["_filename"] = path.name
                data["_path"] = str(path.relative_to(data_dir))
                tactics.append(data)
        except Exception:
            continue
    return tactics


def load_report(data_dir: Path, rel_path: str) -> dict | None:
    """Load a single report by its relative path. Prevents path traversal."""
    try:
        target = (data_dir / rel_path).resolve()
        if not str(target).startswith(str(data_dir.resolve())):
            return None  # path traversal attempt
        data = json.loads(target.read_text(encoding="utf-8"))
        if "summary" in data and "tactics" in data:
            return data
    except Exception:
        pass
    return None


def load_report_by_id(data_dir: Path, incident_id: str, lang: str = "en") -> dict | None:
    """Load a report by incident_id and language code.

    Scans all grouped reports, finds the one matching ``incident_id``, then
    returns the variant for ``lang``.  Falls back to English if the requested
    language is not available.

    Returns:
        Report dict with ``_langs`` populated, or ``None`` if not found.
    """
    reports = scan_reports(data_dir)
    for r in reports:
        if r.get("incident_id") != incident_id:
            continue
        langs = r.get("_langs", {})
        # Try requested lang, then fall back to en, then take any available
        target_path = langs.get(lang) or langs.get("en") or next(iter(langs.values()), None)
        if target_path:
            loaded = load_report(data_dir, target_path)
            if loaded:
                loaded["_langs"] = langs
                loaded["_path"] = target_path
                return loaded
        return r  # return canonical if path load fails
    return None


def load_tactic(data_dir: Path, rel_path: str) -> dict | None:
    """Load a single tactic YAML by its relative path. Prevents path traversal."""
    try:
        target = (data_dir / rel_path).resolve()
        if not str(target).startswith(str(data_dir.resolve())):
            return None
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        if isinstance(data, dict) and str(data.get("id", "")).startswith("tac-"):
            return data
    except Exception:
        pass
    return None
