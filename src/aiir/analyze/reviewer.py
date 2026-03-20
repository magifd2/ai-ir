"""Incident response process quality reviewer using LLM."""

from __future__ import annotations

import json

from aiir.llm.client import LLMClient
from aiir.models import IncidentReview


def _build_system_prompt() -> str:
    """Build the system prompt for IR process review.

    Unlike the other analysis modules, this prompt does not require a nonce
    because user-sourced message text is not passed to the LLM — only the
    already-structured report data (summary, activity, roles, tactics) is used.

    Returns:
        System prompt string.
    """
    return """You are an expert incident response process evaluator.
Analyze the provided structured incident report and evaluate the quality of how the team responded.

IMPORTANT: Always respond in English regardless of the language of the input.

Focus on the PROCESS (how the team worked), not the technical content of the incident itself.
Assess these dimensions:
- Phase timing: estimate how long each IR phase took and whether the pace was appropriate
- Communication quality: information sharing, delays, silos, escalation timeliness
- Role clarity: whether roles were well-defined, IC presence, gaps or overlaps
- Tool appropriateness: whether the right tools and methods were used.
  Each tactic in the report carries a "confidence" field — use it as follows:
    * "confirmed": tool output or explicit results were shared in the channel.
      Treat these as tools that were definitely used; evaluate their appropriateness.
    * "inferred": a participant mentioned using the tool but shared no output.
      Note these as likely used but acknowledge the lack of direct evidence.
    * "suggested": proposed as a recommendation only; do NOT treat as having been used.
  Base your overall tool_appropriateness assessment only on "confirmed" tactics.
  If the only evidence for a tool is "inferred" or "suggested", say so explicitly.
- Strengths: concrete things the team did well
- Improvements: specific, actionable suggestions for next time
- Next-incident checklist: prioritised preparation items

Respond with valid JSON matching this schema:
{
  "incident_id": "string",
  "channel": "string",
  "overall_score": "excellent|good|adequate|poor",
  "phases": [
    {
      "phase": "detection|initial_response|containment|resolution",
      "estimated_duration": "human-readable string or 'unknown'",
      "quality": "good|adequate|poor|unknown",
      "notes": "brief evaluation"
    }
  ],
  "communication": {
    "overall": "overall assessment",
    "delays_observed": ["..."],
    "silos_observed": ["..."]
  },
  "role_clarity": {
    "ic_identified": true,
    "ic_name": "username or null",
    "gaps": ["..."],
    "overlaps": ["..."]
  },
  "tool_appropriateness": "assessment of tool and method choices",
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["specific actionable improvement 1"],
  "checklist": [
    {"item": "checklist item", "priority": "high|medium|low"}
  ]
}"""


def _format_report_for_review(report: dict) -> str:
    """Serialize the structured sections of a report dict for LLM input.

    Deliberately excludes raw message text to avoid re-exposing user data
    and to minimise token consumption. Only the already-analysed fields
    (summary, activity, roles, tactics) are included.

    Args:
        report: Report dict as produced by ``aiir report --format json``.

    Returns:
        Compact JSON string suitable for inclusion in the LLM prompt.
    """
    payload = {
        "channel": report.get("metadata", {}).get("channel", report.get("channel", "")),
        "incident_id": report.get("incident_id", ""),
        "summary": report.get("summary", {}),
        "activity": report.get("activity", {}),
        "roles": report.get("roles", {}),
        "tactics": report.get("tactics", []),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def review_incident(report: dict, client: LLMClient) -> IncidentReview:
    """Generate a process quality review from a completed incident report.

    Args:
        report: Report dict as produced by ``aiir report --format json``.
        client: Configured LLM client.

    Returns:
        Structured IncidentReview model.
    """
    system_prompt = _build_system_prompt()
    channel = report.get("metadata", {}).get("channel", report.get("channel", ""))
    report_text = _format_report_for_review(report)

    user_prompt = f"""Evaluate the incident response process quality for channel {channel}:

{report_text}

Provide a structured process quality review."""

    response_json = client.complete_json(system_prompt, user_prompt)
    try:
        data = json.loads(response_json)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON for incident review: {e}\n"
            f"Response (first 500 chars): {response_json[:500]}"
        ) from e

    # Fill in fields the LLM may have omitted
    data.setdefault("incident_id", report.get("incident_id", ""))
    data.setdefault("channel", channel)
    return IncidentReview.model_validate(data)


def format_review_markdown(review: IncidentReview) -> str:
    """Format an IncidentReview as Markdown.

    Args:
        review: Process review to format.

    Returns:
        Markdown-formatted string.
    """
    lines = [
        "# Incident Response Process Review",
        "",
        f"**Channel**: {review.channel}",
        f"**Overall Score**: {review.overall_score or '—'}",
        "",
    ]

    if review.phases:
        lines += ["## Phase Assessment", ""]
        lines += ["| Phase | Duration | Quality | Notes |"]
        lines += ["|-------|----------|---------|-------|"]
        for ph in review.phases:
            notes = ph.notes.replace("|", "\\|").replace("\n", "<br>")
            lines.append(
                f"| {ph.phase} | {ph.estimated_duration} | {ph.quality.upper()} | {notes} |"
            )
        lines.append("")

    comm = review.communication
    if comm.overall or comm.delays_observed or comm.silos_observed:
        lines += ["## Communication Quality", ""]
        if comm.overall:
            lines += [comm.overall, ""]
        if comm.delays_observed:
            lines += ["**Delays observed:**"]
            for d in comm.delays_observed:
                lines.append(f"- {d}")
            lines.append("")
        if comm.silos_observed:
            lines += ["**Silos observed:**"]
            for s in comm.silos_observed:
                lines.append(f"- {s}")
            lines.append("")

    rc = review.role_clarity
    lines += ["## Role Clarity", ""]
    ic_line = f"**Incident Commander**: {rc.ic_name}" if rc.ic_identified and rc.ic_name else "**Incident Commander**: not clearly identified"
    lines += [ic_line, ""]
    if rc.gaps:
        lines += ["**Gaps:**"]
        for g in rc.gaps:
            lines.append(f"- {g}")
        lines.append("")
    if rc.overlaps:
        lines += ["**Overlaps:**"]
        for o in rc.overlaps:
            lines.append(f"- {o}")
        lines.append("")

    if review.tool_appropriateness:
        lines += ["## Tool Appropriateness", "", review.tool_appropriateness, ""]

    if review.strengths:
        lines += ["## Strengths", ""]
        for s in review.strengths:
            lines.append(f"- {s}")
        lines.append("")

    if review.improvements:
        lines += ["## Improvements", ""]
        for i in review.improvements:
            lines.append(f"- {i}")
        lines.append("")

    if review.checklist:
        lines += ["## Next-Incident Checklist", ""]
        priority_order = {"high": 0, "medium": 1, "low": 2}
        for item in sorted(review.checklist, key=lambda x: priority_order.get(x.priority, 1)):
            lines.append(f"- [{item.priority.upper()}] {item.item}")
        lines.append("")

    return "\n".join(lines)
