"""ai-ir CLI - Incident Response Analysis Toolset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from aiir import __version__

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_or_preprocess(input_file: Path) -> "ProcessedExport":
    """Load a file as ProcessedExport, preprocessing if it is a raw export.

    Detects format by checking for the ``security_warnings`` key which is
    present only in preprocessed output.

    Args:
        input_file: Path to JSON file (raw export or preprocessed).

    Returns:
        ProcessedExport ready for analysis.
    """
    from aiir.models import ProcessedExport

    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    if "security_warnings" in data:
        # Already preprocessed
        return ProcessedExport.model_validate(data)
    else:
        # Raw scat/stail export — run ingest pipeline
        err_console.print(
            "[yellow]Input is a raw export. Running preprocessing automatically...[/yellow]"
        )
        from aiir.models import SlackExport

        export = SlackExport.model_validate(data)
        return _preprocess_export(export)


def _preprocess_export(export: "SlackExport") -> "ProcessedExport":
    """Run the full preprocessing pipeline on a raw SlackExport.

    Generates a single cryptographically random nonce for the entire export.
    Every message is wrapped in ``<user_message_{nonce}>`` tags using this
    shared nonce so LLM system prompts can reference it consistently.

    Args:
        export: Raw Slack export.

    Returns:
        ProcessedExport with defanged IoCs, nonce-tagged sanitized text,
        and the nonce stored in ``sanitization_nonce``.
    """
    from aiir.models import IoC, ProcessedExport, ProcessedMessage
    from aiir.parser.defang import defang_text
    from aiir.parser.sanitizer import generate_nonce, sanitize_for_llm

    # One nonce shared across all messages in this export session.
    # Using a single nonce means the LLM system prompt can reference one tag
    # name for the entire conversation rather than per-message tag names.
    nonce = generate_nonce()
    err_console.print(f"[dim]Generated sanitization nonce: {nonce[:4]}...{nonce[-4:]}[/dim]")

    processed_messages = []
    all_security_warnings = []

    for msg in export.messages:
        # 1. Defang IoCs
        defanged_text, iocs = defang_text(msg.text)

        # 2. Sanitize for LLM (pass shared nonce)
        sanitization = sanitize_for_llm(defanged_text, nonce=nonce)

        if sanitization.has_risk:
            warnings = [f"@{msg.user_name}: {w}" for w in sanitization.warnings]
            all_security_warnings.extend(warnings)
            for w in warnings:
                err_console.print(f"[red][SECURITY WARNING] Injection risk detected: {w}[/red]")

        if iocs:
            ioc_summary = ", ".join(f"{ioc.type}:{ioc.original}" for ioc in iocs[:5])
            if len(iocs) > 5:
                ioc_summary += f" ... and {len(iocs) - 5} more"
            err_console.print(
                f"[yellow][DEFANG] @{msg.user_name}: defanged {len(iocs)} IoC(s): {ioc_summary}[/yellow]"
            )

        processed_msg = ProcessedMessage(
            user_id=msg.user_id,
            user_name=msg.user_name,
            post_type=msg.post_type,
            timestamp=msg.timestamp,
            timestamp_unix=msg.timestamp_unix,
            text=sanitization.text,
            files=msg.files,
            thread_timestamp_unix=msg.thread_timestamp_unix,
            is_reply=msg.is_reply,
            iocs=iocs,
            has_injection_risk=sanitization.has_risk,
            injection_warnings=sanitization.warnings,
        )
        processed_messages.append(processed_msg)

    return ProcessedExport(
        export_timestamp=export.export_timestamp,
        channel_name=export.channel_name,
        messages=processed_messages,
        security_warnings=all_security_warnings,
        sanitization_nonce=nonce,
    )


def _get_llm_client() -> "LLMClient":
    """Create and return an LLM client using current configuration.

    Raises:
        SystemExit: If AIIR_LLM_API_KEY is not configured.
    """
    from aiir.config import get_llm_config
    from aiir.llm.client import LLMClient

    try:
        config = get_llm_config()
    except ValueError as e:
        err_console.print(f"[red][ERROR] {e}[/red]")
        sys.exit(1)

    return LLMClient(config)


def _write_output(content: str, output: Path | None) -> None:
    """Write content to file or stdout.

    Args:
        content: String to write.
        output: Output file path, or None for stdout.
    """
    if output:
        output.write_text(content, encoding="utf-8")
        err_console.print(f"[green]Output written to {output}[/green]")
    else:
        print(content)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version=__version__, prog_name="aiir")
def main() -> None:
    """ai-ir: AI-powered Incident Response Analysis Toolset.

    Analyzes incident response Slack conversation history exported from
    scat or stail to generate summaries, activity reports, role analysis,
    and reusable investigation knowledge.
    """


# ---------------------------------------------------------------------------
# config subgroup
# ---------------------------------------------------------------------------


@main.group("config")
def config_group() -> None:
    """Manage aiir configuration and credentials."""


@config_group.command("set-key")
@click.option(
    "--key",
    "-k",
    default=None,
    help="API key (omit to be prompted securely).",
)
def config_set_key(key: str | None) -> None:
    """Store the LLM API key in the system keychain.

    On macOS this writes to the login Keychain. The key is then used
    automatically without needing AIIR_LLM_API_KEY in the environment.

    If --key is omitted you will be prompted to enter it securely (no echo).
    """
    from aiir.keychain import set_api_key

    if key is None:
        key = click.prompt("LLM API key", hide_input=True)

    try:
        set_api_key(key)
        err_console.print("[green]API key stored in system keychain.[/green]")
        err_console.print(
            "[dim]It will be used automatically when AIIR_LLM_API_KEY is not set.[/dim]"
        )
    except (ImportError, RuntimeError) as e:
        err_console.print(f"[red][ERROR] {e}[/red]")
        sys.exit(1)


@config_group.command("delete-key")
def config_delete_key() -> None:
    """Remove the LLM API key from the system keychain."""
    from aiir.keychain import delete_api_key

    try:
        delete_api_key()
        err_console.print("[green]API key removed from system keychain.[/green]")
    except (ImportError, RuntimeError) as e:
        err_console.print(f"[red][ERROR] {e}[/red]")
        sys.exit(1)


@config_group.command("show")
def config_show() -> None:
    """Show current configuration (API key is masked)."""
    import platform

    from aiir.config import get_config
    from aiir.keychain import get_api_key, is_keyring_available

    cfg = get_config()

    # Determine API key source
    env_key = cfg.llm.api_key
    keyring_key = get_api_key() if is_keyring_available() else None

    if env_key:
        key_source = "environment / .env"
        key_display = env_key[:8] + "..." if len(env_key) > 8 else "***"
    elif keyring_key:
        key_source = "system keychain"
        key_display = keyring_key[:8] + "..." if len(keyring_key) > 8 else "***"
    else:
        key_source = "NOT SET"
        key_display = "(none)"

    lines = [
        f"Platform:      {platform.system()} {platform.release()}",
        f"LLM Base URL:  {cfg.llm.base_url}",
        f"LLM Model:     {cfg.llm.model}",
        f"API Key:       {key_display}  [{key_source}]",
        f"Keyring avail: {is_keyring_available()}",
    ]

    err_console.print(Panel("\n".join(lines), title="[bold]aiir configuration[/bold]"))


# ---------------------------------------------------------------------------
# ingest command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: stdout)",
)
def ingest(input_file: Path, output: Path | None) -> None:
    """Parse and preprocess a scat/stail JSON export file.

    Performs IoC defanging (IPs, URLs, emails, hashes) and prompt injection
    detection. Outputs a preprocessed JSON file ready for analysis commands.
    """
    from aiir.models import ProcessedExport, SlackExport
    from aiir.parser.loader import load_export

    try:
        raw_export = load_export(input_file)
    except Exception as e:
        err_console.print(f"[red][ERROR] Failed to load {input_file}: {e}[/red]")
        sys.exit(1)

    processed = _preprocess_export(raw_export)

    output_json = processed.model_dump_json(indent=2)
    _write_output(output_json, output)

    total_iocs = sum(len(msg.iocs) for msg in processed.messages)
    risky_msgs = sum(1 for msg in processed.messages if msg.has_injection_risk)

    err_console.print(
        Panel(
            f"Processed {len(processed.messages)} messages\n"
            f"Defanged {total_iocs} IoC(s)\n"
            f"Injection risks detected: {risky_msgs} message(s)",
            title="[bold green]Ingest Complete[/bold green]",
        )
    )


# ---------------------------------------------------------------------------
# summarize command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: stdout)",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    help="Output format",
)
def summarize(input_file: Path, output: Path | None, fmt: str) -> None:
    """Generate an incident summary using LLM.

    Accepts either a raw scat/stail export or preprocessed JSON from 'aiir ingest'.
    """
    from aiir.analyze.summarizer import format_summary_markdown, summarize_incident

    processed = _load_or_preprocess(input_file)
    client = _get_llm_client()

    err_console.print("[cyan]Generating incident summary...[/cyan]")
    summary = summarize_incident(processed, client)

    if fmt == "json":
        content = json.dumps(summary.model_dump(), indent=2, ensure_ascii=False)
    else:
        content = format_summary_markdown(summary)

    _write_output(content, output)


# ---------------------------------------------------------------------------
# activity command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
)
def activity(input_file: Path, output: Path | None, fmt: str) -> None:
    """Analyze per-participant activities using LLM.

    Identifies each participant's actions, methods used, and findings.
    """
    from aiir.analyze.activity import analyze_activity, format_activity_markdown

    processed = _load_or_preprocess(input_file)
    client = _get_llm_client()

    err_console.print("[cyan]Analyzing participant activities...[/cyan]")
    analysis = analyze_activity(processed, client)

    if fmt == "json":
        content = json.dumps(analysis.model_dump(), indent=2, ensure_ascii=False)
    else:
        content = format_activity_markdown(analysis)

    _write_output(content, output)


# ---------------------------------------------------------------------------
# roles command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
)
def roles(input_file: Path, output: Path | None, fmt: str) -> None:
    """Infer participant roles and relationships using LLM.

    Identifies incident response roles (Incident Commander, Lead Responder, etc.)
    and relationships between participants.
    """
    from aiir.analyze.roles import analyze_roles, format_roles_markdown

    processed = _load_or_preprocess(input_file)
    client = _get_llm_client()

    err_console.print("[cyan]Inferring participant roles and relationships...[/cyan]")
    analysis = analyze_roles(processed, client)

    if fmt == "json":
        content = json.dumps(analysis.model_dump(), indent=2, ensure_ascii=False)
    else:
        content = format_roles_markdown(analysis)

    _write_output(content, output)


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: stdout). Ignored when --knowledge-only is set.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    help="Report output format. Ignored when --knowledge-only is set.",
)
@click.option(
    "--knowledge-dir",
    "-k",
    type=click.Path(path_type=Path),
    default=None,
    help="Also save extracted tactics as YAML files to this directory.",
)
@click.option(
    "--knowledge-only",
    is_flag=True,
    default=False,
    help=(
        "Extract and save tactics only — skip summary, activity, and roles analysis. "
        "Requires --knowledge-dir."
    ),
)
def report(
    input_file: Path,
    output: Path | None,
    fmt: str,
    knowledge_dir: Path | None,
    knowledge_only: bool,
) -> None:
    """Generate a comprehensive incident analysis report.

    Runs all analyses (summary, activity, roles, tactics) and combines them
    into a single report document.

    Use --knowledge-only to extract and save investigation tactics without
    generating a full report. Use --knowledge-dir to save tactics as YAML
    alongside the full report.

    Examples:

        # Full report (Markdown)
        aiir report incident.json -o report.md

        # Full report (JSON) + save tactics as YAML
        aiir report incident.json --format json -o report.json -k ./knowledge

        # Tactics only
        aiir report incident.json --knowledge-only -k ./knowledge
    """
    from aiir.knowledge.extractor import extract_tactics
    from aiir.knowledge.formatter import save_tactics

    if knowledge_only and not knowledge_dir:
        err_console.print(
            "[red][ERROR] --knowledge-only requires --knowledge-dir (-k).[/red]"
        )
        sys.exit(1)

    processed = _load_or_preprocess(input_file)
    client = _get_llm_client()

    if knowledge_only:
        err_console.print("[cyan]Extracting investigation tactics...[/cyan]")
        tactics = extract_tactics(processed, client)
        if not tactics:
            err_console.print("[yellow]No tactics extracted from the conversation.[/yellow]")
            return
        saved_paths = save_tactics(tactics, knowledge_dir)
        err_console.print(
            Panel(
                "\n".join(f"  {p.name}" for p in saved_paths),
                title=f"[bold green]Saved {len(saved_paths)} tactic(s) to {knowledge_dir}[/bold green]",
            )
        )
        return

    # Full report
    from aiir.analyze.activity import analyze_activity
    from aiir.analyze.roles import analyze_roles
    from aiir.analyze.summarizer import summarize_incident
    from aiir.report.generator import generate_json_report, generate_markdown_report

    err_console.print("[cyan]Running full incident analysis...[/cyan]")

    err_console.print("  [dim]1/4 Generating summary...[/dim]")
    summary = summarize_incident(processed, client)

    err_console.print("  [dim]2/4 Analyzing activities...[/dim]")
    activity_analysis = analyze_activity(processed, client)

    err_console.print("  [dim]3/4 Inferring roles...[/dim]")
    roles_analysis = analyze_roles(processed, client)

    err_console.print("  [dim]4/4 Extracting tactics...[/dim]")
    tactics = extract_tactics(processed, client)

    if fmt == "json":
        report_data = generate_json_report(
            processed, summary, activity_analysis, roles_analysis, tactics
        )
        content = json.dumps(report_data, indent=2, ensure_ascii=False)
    else:
        content = generate_markdown_report(
            processed, summary, activity_analysis, roles_analysis, tactics
        )

    _write_output(content, output)

    if knowledge_dir:
        saved_paths = save_tactics(tactics, knowledge_dir)
        err_console.print(
            f"[green]Saved {len(saved_paths)} tactic(s) to {knowledge_dir}[/green]"
        )

    err_console.print(
        Panel(
            f"Summary: {summary.title}\n"
            f"Participants analyzed: {len(activity_analysis.participants)}\n"
            f"Roles inferred: {len(roles_analysis.participants)}\n"
            f"Tactics extracted: {len(tactics)}",
            title="[bold green]Report Complete[/bold green]",
        )
    )


# ---------------------------------------------------------------------------
# translate command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("report_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--lang",
    "-l",
    required=True,
    help="Target language code (e.g. ja, zh, de, fr, es, ko).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: <stem>.<lang>.json next to input).",
)
def translate(report_file: Path, lang: str, output: Path | None) -> None:
    """Translate a report JSON into another language.

    Translates narrative fields (title, summary, procedure, etc.) while
    preserving technical content: tool names, commands, IOCs, IDs, tags.

    The source report JSON (English) is not modified. A new file is saved
    alongside it with the language code in the filename, e.g. report.ja.json.

    Example:

        aiir translate report.json --lang ja
    """
    from aiir.translate.translator import SUPPORTED_LANGS, translate_report

    with open(report_file, encoding="utf-8") as f:
        report_data = json.load(f)

    if "summary" not in report_data or "tactics" not in report_data:
        err_console.print(
            "[red][ERROR] Input does not look like an aiir report JSON "
            "(missing 'summary' or 'tactics' keys).[/red]"
        )
        sys.exit(1)

    if output is None:
        output = report_file.parent / f"{report_file.stem}.{lang}.json"

    client = _get_llm_client()

    err_console.print(
        f"[cyan]Translating report into {lang} "
        f"({'known' if lang in SUPPORTED_LANGS else 'custom'} language)...[/cyan]"
    )
    err_console.print("  [dim]1/4 Translating summary...[/dim]")
    err_console.print("  [dim]2/4 Translating activity...[/dim]")
    err_console.print("  [dim]3/4 Translating roles...[/dim]")
    err_console.print("  [dim]4/4 Translating tactics...[/dim]")

    translated = translate_report(report_data, lang, client)
    content = json.dumps(translated, indent=2, ensure_ascii=False)
    _write_output(content, output)

    err_console.print(
        Panel(
            f"Language:    {lang}\n"
            f"Source:      {report_file}\n"
            f"Output:      {output}",
            title="[bold green]Translation Complete[/bold green]",
        )
    )


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("data_dir", type=click.Path(path_type=Path), default=Path("."))
@click.option("--port", "-p", default=8765, show_default=True, help="Port to listen on (localhost only)")
@click.option("--no-browser", is_flag=True, help="Do not open browser automatically")
def serve(data_dir: Path, port: int, no_browser: bool) -> None:
    """Start local web UI for browsing analysis results.

    Scans DATA_DIR (default: current directory) for report JSON files
    and knowledge YAML files, then starts a read-only web server on
    http://localhost:{port}.

    Security: always binds to 127.0.0.1 only.
    """
    import uvicorn
    from aiir.server.app import create_app

    data_dir = data_dir.resolve()
    if not data_dir.exists():
        err_console.print(f"[red][ERROR] Directory not found: {data_dir}[/red]")
        sys.exit(1)

    app = create_app(data_dir)
    url = f"http://localhost:{port}"

    err_console.print(
        Panel(
            f"URL:      {url}\n"
            f"Data dir: {data_dir}\n\n"
            f"[dim]Ctrl+C to stop[/dim]",
            title="[bold green]ai-ir Web UI[/bold green]",
        )
    )

    if not no_browser:
        import threading
        import webbrowser
        import time

        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
