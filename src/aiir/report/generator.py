"""Full incident report generator."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from aiir.models import (
    ActivityAnalysis,
    IncidentSummary,
    ProcessedExport,
    RoleAnalysis,
    Tactic,
)


def make_incident_id(export: ProcessedExport) -> str:
    """Generate a deterministic incident ID from channel name and export timestamp.

    The same source data always produces the same ID, so translated versions
    of a report share an identical incident_id and are recognized as one incident.

    Returns:
        12-character lowercase hex string (48-bit SHA-256 prefix).
    """
    key = f"{export.channel_name}|{export.export_timestamp.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def generate_markdown_report(
    export: ProcessedExport,
    summary: IncidentSummary,
    activity: ActivityAnalysis,
    roles: RoleAnalysis,
    tactics: list[Tactic],
) -> str:
    """Generate a comprehensive Markdown report combining all analyses.

    Args:
        export: The preprocessed Slack export.
        summary: Incident summary from the summarizer.
        activity: Per-participant activity analysis.
        roles: Role and relationship inference results.
        tactics: List of extracted investigation tactics.

    Returns:
        Markdown-formatted report string.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# Incident Analysis Report",
        "",
        f"**Channel**: {export.channel_name}",
        f"**Generated**: {now}",
        f"**Export Timestamp**: {export.export_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "---",
        "",
    ]

    # --- Summary Section ---
    lines.append(f"## Incident Summary: {summary.title}")
    lines.append("")
    lines.append(f"**Severity**: {summary.severity or 'Unknown'}")
    lines.append("")

    if summary.affected_systems:
        lines.append("**Affected Systems:**")
        for system in summary.affected_systems:
            lines.append(f"- {system}")
        lines.append("")

    if summary.summary:
        lines.append(summary.summary)
        lines.append("")

    if summary.timeline:
        lines.append("### Timeline")
        lines.append("")
        lines.append("| Time | Actor | Event |")
        lines.append("|------|-------|-------|")
        for event in summary.timeline:
            lines.append(f"| {event.timestamp} | {event.actor} | {event.event} |")
        lines.append("")

    if summary.root_cause:
        lines.append("### Root Cause")
        lines.append(summary.root_cause)
        lines.append("")

    if summary.resolution:
        lines.append("### Resolution")
        lines.append(summary.resolution)
        lines.append("")

    lines.append("---")
    lines.append("")

    # --- Activity Section ---
    lines.append("## Participant Activities")
    lines.append("")

    for participant in activity.participants:
        lines.append(f"### @{participant.user_name}")
        lines.append(f"**Role**: {participant.role_hint}")
        lines.append("")

        if participant.actions:
            lines.append("| Time | Purpose | Method | Findings |")
            lines.append("|------|---------|--------|----------|")
            for action in participant.actions:
                purpose = action.purpose.replace("|", "\\|")
                method = action.method.replace("|", "\\|")
                findings = action.findings.replace("|", "\\|")
                lines.append(
                    f"| {action.timestamp} | {purpose} | {method} | {findings} |"
                )
            lines.append("")

    lines.append("---")
    lines.append("")

    # --- Roles Section ---
    lines.append("## Roles and Relationships")
    lines.append("")

    if roles.participants:
        lines.append("### Participant Roles")
        lines.append("")
        for participant in roles.participants:
            confidence_label = {
                "high": "(High confidence)",
                "medium": "(Medium confidence)",
                "low": "(Low confidence)",
            }.get(participant.confidence, "")
            lines.append(
                f"- **@{participant.user_name}**: {participant.inferred_role} {confidence_label}"
            )
            for ev in participant.evidence:
                lines.append(f"  - _{ev}_")
        lines.append("")

    if roles.relationships:
        lines.append("### Relationships")
        lines.append("")
        lines.append("| From | Relationship | To |")
        lines.append("|------|-------------|----|")
        for rel in roles.relationships:
            lines.append(
                f"| @{rel.from_user} | {rel.relationship_type} | @{rel.to_user} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")

    # --- Knowledge Section ---
    if tactics:
        lines.append("## Extracted Investigation Tactics")
        lines.append("")
        for tactic in tactics:
            lines.append(f"### {tactic.id}: {tactic.title}")
            lines.append(f"**Category**: {tactic.category}")
            lines.append(f"**Purpose**: {tactic.purpose}")
            lines.append("")

            if tactic.tools:
                lines.append(f"**Tools**: {', '.join(f'`{t}`' for t in tactic.tools)}")
                lines.append("")

            lines.append("**Procedure:**")
            lines.append(tactic.procedure)
            lines.append("")

            lines.append("**Observations:**")
            lines.append(tactic.observations)
            lines.append("")

            if tactic.tags:
                lines.append(f"**Tags**: {', '.join(tactic.tags)}")
                lines.append("")

    return "\n".join(lines)


def generate_json_report(
    export: ProcessedExport,
    summary: IncidentSummary,
    activity: ActivityAnalysis,
    roles: RoleAnalysis,
    tactics: list[Tactic],
    lang: str = "en",
) -> dict:
    """Generate a JSON report combining all analyses.

    Args:
        export: The preprocessed Slack export.
        summary: Incident summary from the summarizer.
        activity: Per-participant activity analysis.
        roles: Role and relationship inference results.
        tactics: List of extracted investigation tactics.
        lang: Language code of the report's narrative content (default ``"en"``).

    Returns:
        Dictionary suitable for JSON serialization.
    """
    return {
        "incident_id": make_incident_id(export),
        "lang": lang,
        "metadata": {
            "channel": export.channel_name,
            "export_timestamp": export.export_timestamp.isoformat(),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "message_count": len(export.messages),
            "security_warnings": export.security_warnings,
        },
        "summary": summary.model_dump(),
        "activity": activity.model_dump(),
        "roles": roles.model_dump(),
        "tactics": [t.model_dump() for t in tactics],
    }
