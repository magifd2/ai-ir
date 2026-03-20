"""Translate analysis report JSON into a target language."""

from __future__ import annotations

import json
from typing import Any

from aiir.llm.client import LLMClient

# Fields to translate per section (narrative text only).
# Technical identifiers (tool names, commands, IDs, tags, IOCs) are NOT translated.
_TRANSLATE_INSTRUCTIONS = """\
You are a professional technical translator.
Translate the JSON values below into {lang_name}.

Rules:
- Translate ONLY the string values in the JSON.
- Do NOT translate keys, usernames, channel names, or any value that looks like:
  - A shell command or code snippet (e.g., text inside backticks: `grep`, `journalctl -u sshd`)
  - An IP address, domain, URL, file hash, or other indicator of compromise
  - A severity level word: critical, high, medium, low, unknown
  - A confidence word: high, medium, low
  - A relationship type: reports_to, coordinates_with, escalated_to, informed
  - A category slug (kebab-case like log-analysis, linux-auditd)
  - A tactic ID (e.g., tac-20260319-001)
  - An ISO date or timestamp
- Preserve all whitespace and newlines within values.
- Return valid JSON with the exact same structure as the input.
"""

_LANG_NAMES: dict[str, str] = {
    "ja": "Japanese",
    "zh": "Simplified Chinese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
}


def _lang_name(lang: str) -> str:
    return _LANG_NAMES.get(lang, lang)


def _translate_chunk(data: Any, lang: str, client: LLMClient) -> Any:
    """Send a JSON chunk to the LLM for translation and return the parsed result."""
    system_prompt = _TRANSLATE_INSTRUCTIONS.format(lang_name=_lang_name(lang))
    user_prompt = json.dumps(data, ensure_ascii=False)
    raw = client.complete_json(system_prompt, user_prompt)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Section-level translators
# ---------------------------------------------------------------------------

def _translate_summary(summary: dict[str, Any], lang: str, client: LLMClient) -> dict[str, Any]:
    """Translate narrative fields in the summary section."""
    payload = {
        "title": summary.get("title", ""),
        "root_cause": summary.get("root_cause", ""),
        "resolution": summary.get("resolution", ""),
        "summary": summary.get("summary", ""),
        "timeline": [
            {"timestamp": e["timestamp"], "actor": e["actor"], "event": e["event"]}
            for e in summary.get("timeline", [])
        ],
    }
    translated = _translate_chunk(payload, lang, client)
    result = dict(summary)
    result.update({
        "title": translated.get("title", summary.get("title", "")),
        "root_cause": translated.get("root_cause", summary.get("root_cause", "")),
        "resolution": translated.get("resolution", summary.get("resolution", "")),
        "summary": translated.get("summary", summary.get("summary", "")),
    })
    orig_timeline = summary.get("timeline", [])
    trans_timeline = translated.get("timeline", [])
    merged_timeline = []
    for i, orig_ev in enumerate(orig_timeline):
        ev = dict(orig_ev)
        if i < len(trans_timeline):
            ev["event"] = trans_timeline[i].get("event", orig_ev.get("event", ""))
        merged_timeline.append(ev)
    result["timeline"] = merged_timeline
    return result


def _translate_activity(activity: dict[str, Any], lang: str, client: LLMClient) -> dict[str, Any]:
    """Translate narrative fields in the activity section."""
    participants = activity.get("participants", [])
    payload = {
        "participants": [
            {
                "user_name": p["user_name"],
                "role_hint": p.get("role_hint", ""),
                "actions": [
                    {
                        "timestamp": a["timestamp"],
                        "purpose": a.get("purpose", ""),
                        "findings": a.get("findings", ""),
                    }
                    for a in p.get("actions", [])
                ],
            }
            for p in participants
        ]
    }
    translated = _translate_chunk(payload, lang, client)
    result = dict(activity)
    orig_parts = participants
    trans_parts = translated.get("participants", [])
    merged = []
    for i, orig_p in enumerate(orig_parts):
        p = dict(orig_p)
        if i < len(trans_parts):
            tp = trans_parts[i]
            p["role_hint"] = tp.get("role_hint", orig_p.get("role_hint", ""))
            orig_actions = orig_p.get("actions", [])
            trans_actions = tp.get("actions", [])
            merged_actions = []
            for j, orig_a in enumerate(orig_actions):
                a = dict(orig_a)
                if j < len(trans_actions):
                    ta = trans_actions[j]
                    a["purpose"] = ta.get("purpose", orig_a.get("purpose", ""))
                    a["findings"] = ta.get("findings", orig_a.get("findings", ""))
                merged_actions.append(a)
            p["actions"] = merged_actions
        merged.append(p)
    result["participants"] = merged
    return result


def _translate_roles(roles: dict[str, Any], lang: str, client: LLMClient) -> dict[str, Any]:
    """Translate narrative fields in the roles section."""
    participants = roles.get("participants", [])
    relationships = roles.get("relationships", [])
    payload = {
        "participants": [
            {
                "user_name": p["user_name"],
                "inferred_role": p.get("inferred_role", ""),
                "evidence": p.get("evidence", []),
            }
            for p in participants
        ],
        "relationships": [
            {"from_user": r["from_user"], "to_user": r.get("to_user"), "description": r.get("description", "")}
            for r in relationships
        ],
    }
    translated = _translate_chunk(payload, lang, client)
    result = dict(roles)
    orig_parts = participants
    trans_parts = translated.get("participants", [])
    merged_parts = []
    for i, orig_p in enumerate(orig_parts):
        p = dict(orig_p)
        if i < len(trans_parts):
            tp = trans_parts[i]
            p["inferred_role"] = tp.get("inferred_role", orig_p.get("inferred_role", ""))
            p["evidence"] = tp.get("evidence", orig_p.get("evidence", []))
        merged_parts.append(p)
    result["participants"] = merged_parts
    orig_rels = relationships
    trans_rels = translated.get("relationships", [])
    merged_rels = []
    for i, orig_r in enumerate(orig_rels):
        r = dict(orig_r)
        if i < len(trans_rels):
            r["description"] = trans_rels[i].get("description", orig_r.get("description", ""))
        merged_rels.append(r)
    result["relationships"] = merged_rels
    return result


def _translate_tactics(tactics: list[dict[str, Any]], lang: str, client: LLMClient) -> list[dict[str, Any]]:
    """Translate narrative fields in the tactics list."""
    payload = {
        "tactics": [
            {
                "title": t.get("title", ""),
                "purpose": t.get("purpose", ""),
                "procedure": t.get("procedure", ""),
                "observations": t.get("observations", ""),
            }
            for t in tactics
        ]
    }
    translated = _translate_chunk(payload, lang, client)
    trans_tactics = translated.get("tactics", [])
    result = []
    for i, orig_t in enumerate(tactics):
        t = dict(orig_t)
        if i < len(trans_tactics):
            tt = trans_tactics[i]
            t["title"] = tt.get("title", orig_t.get("title", ""))
            t["purpose"] = tt.get("purpose", orig_t.get("purpose", ""))
            t["procedure"] = tt.get("procedure", orig_t.get("procedure", ""))
            t["observations"] = tt.get("observations", orig_t.get("observations", ""))
        result.append(t)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_LANGS = sorted(_LANG_NAMES.keys())


def translate_report(report: dict[str, Any], lang: str, client: LLMClient) -> dict[str, Any]:
    """Translate all narrative fields of a report dict into the target language.

    Technical fields (tool names, commands, IDs, tags, IOCs) are preserved as-is.
    Translation is performed section by section to keep each LLM call focused.

    Args:
        report: Report dict as produced by ``aiir report``.
        lang: BCP-47 language code (e.g. ``"ja"``, ``"zh"``, ``"de"``).
        client: Configured LLM client.

    Returns:
        A new dict with narrative fields translated; all other fields unchanged.
    """
    result = dict(report)
    result["lang"] = lang
    # Remove the old marker key if present from a previous run
    result.pop("_translated_lang", None)

    if "summary" in report and report["summary"]:
        result["summary"] = _translate_summary(report["summary"], lang, client)

    if "activity" in report and report["activity"]:
        result["activity"] = _translate_activity(report["activity"], lang, client)

    if "roles" in report and report["roles"]:
        result["roles"] = _translate_roles(report["roles"], lang, client)

    if "tactics" in report and report["tactics"]:
        result["tactics"] = _translate_tactics(report["tactics"], lang, client)

    return result
