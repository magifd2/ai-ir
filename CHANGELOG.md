# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-03-20

### Added
- **`aiir review` command**: Analyze a completed report JSON and generate a structured
  assessment of the incident response *process* (not the technical content).
  Evaluates phase timing, communication quality, role clarity, tool appropriateness,
  strengths, and concrete improvement suggestions. Outputs `<stem>.review.json` by
  default so the web dashboard can display it automatically.
- **`src/aiir/analyze/reviewer.py`**: New module with `review_incident()` and
  `format_review_markdown()`. Unlike other analysis modules, it does not re-send raw
  Slack message text to the LLM — only the already-structured report sections
  (summary/activity/roles/tactics) are used, reducing token consumption and
  prompt injection risk.
- **`IncidentReview` models** in `models.py`: `ResponsePhase`, `CommunicationAssessment`,
  `RoleClarity`, `ChecklistItem`, `IncidentReview`.
- **`load_review()` in `server/loader.py`**: Load `<stem>.review.json` alongside a
  report, with path traversal prevention and language-suffix stripping
  (e.g. `report.ja.json` → `report.review.json`).
- **「対応評価」tab in web UI**: When a `.review.json` file is present, a new tab appears
  in the report detail view showing phase assessment table, communication/role clarity
  cards, strengths/improvements columns, and a prioritised next-incident checklist.
  The tab is hidden when no review file exists.
- 19 new tests covering reviewer prompt structure, report formatting, model validation,
  loader review loading, and route tab visibility.

## [1.0.3] - 2026-03-20

### Added
- **`aiir ingest` context-size warning**: After preprocessing, estimates the token count
  of the conversation using a character-based heuristic (chars / 2.5, covering Japanese
  and English text mix). Prints a colour-coded warning panel if the estimate exceeds a
  threshold, with model recommendations:
  - 10K–30K tokens (yellow): caution — approaching local LLM limits (< 32K context)
  - 30K–64K tokens (yellow): warning — exceeds typical local LLM limits; recommend
    cloud LLM with ≥ 64K context (Claude Sonnet 4.5 / 200K, Gemini 2.5 Pro / 1M)
  - > 64K tokens (red): very large export — local LLM analysis will be unreliable;
    large-context cloud model required
  - < 10K tokens: no warning displayed

## [1.0.2] - 2026-03-20

### Changed
- **Web UI: local time display**: Timeline and activity timestamps are now converted
  from UTC to the browser's local timezone via JavaScript (`toLocaleString()`).
  The original UTC value is preserved as a hover tooltip on each timestamp cell.
  Strings that cannot be parsed as a valid date (e.g. relative descriptions from
  the LLM) are left unchanged.

## [1.0.1] - 2026-03-20

### Fixed
- **Markdown table newlines**: Newline characters in LLM-generated table cell content are now
  escaped to `<br>` in all Markdown generators (`report/generator.py`, `analyze/activity.py`,
  `analyze/summarizer.py`, `analyze/roles.py`). Prevents broken table formatting when the LLM
  includes multi-line text in timeline events, activity actions, or relationships.
- **LLM JSON parse errors**: All four analysis modules (`summarizer`, `activity`, `roles`,
  `extractor`) now wrap `json.loads()` in a try-except that raises a `ValueError` with the
  analysis type and the first 500 characters of the LLM response. Produces a diagnostic error
  instead of a raw `JSONDecodeError` traceback.
- **NDJSON line numbers in errors**: `parser/loader.py` now uses `enumerate(f, start=1)` and
  includes the file path and line number in parse error messages, making malformed stail exports
  easier to debug.

### Changed
- **Dependency version upper bounds**: All runtime dependencies now carry explicit major-version
  upper bounds (e.g. `pydantic>=2.0,<3.0`) to prevent silent breakage from future major releases.

## [1.0.0] - 2026-03-20

First official release. Consolidates all pre-release development (v0.1.0–v0.5.0)
into a stable, feature-complete toolset.

### Highlights
- Full incident analysis pipeline: `ingest` → `summarize` / `activity` / `roles` → `report`
- Tactic knowledge extraction and YAML knowledge base via `aiir report --knowledge-dir`
- Multi-language report translation via `aiir translate` (ja / zh / ko / de / fr / es)
- Incident grouping by `incident_id` with language switcher in the web UI
- Local read-only web dashboard (`aiir serve`) with report and knowledge browsing
- Security-first design: IoC defanging, nonce-tagged prompt injection defense
- OpenAI-compatible LLM client with local LLM support (LM Studio, Ollama, etc.)
- LLM response normalization: reasoning block stripping, JSON repair, text-mode fallback
- macOS Keychain integration for API key storage
- stail NDJSON and scat JSON export format support
- Bilingual documentation (English / Japanese)

## [0.5.0] - 2026-03-20

### Added
- **`incident_id` in report JSON**: `aiir report --format json` now embeds a
  deterministic 12-character hex ID derived from channel name + export timestamp.
  Re-running on the same source data always produces the same ID, so translated
  variants of a report share an identical `incident_id`.
- **`lang` field in report JSON**: records the language of the report's narrative
  content (`"en"` for analysis output, `"ja"` etc. for translated copies).
- **`aiir translate` now sets `lang`** on the output and inherits `incident_id`
  from the source report (replacing the removed `_translated_lang` marker).
- **Incident grouping in web UI**: the dashboard groups reports with the same
  `incident_id` into a single card. Language variant badges (EN / JA / …) are
  shown on the card. The report view URL uses `?id=<incident_id>&lang=<code>`.
- **Language switcher in report view**: when multiple language variants exist,
  language buttons appear in the report header. Clicking switches to that variant.
- **`aiir report --knowledge-dir (-k)`**: save extracted tactics as YAML files
  alongside the full report in a single command, ensuring the knowledge base is
  consistent with the report.
- **`aiir report --knowledge-only`**: extract and save tactics only (skip summary,
  activity, roles analysis). Requires `--knowledge-dir`.
- `load_report_by_id()` in `server/loader.py`: load a report by `incident_id` and
  language code, with English fallback.
- 5 new tests for `incident_id` grouping and `load_report_by_id()`.

### Removed
- **`aiir knowledge` command**: removed to eliminate confusion between its
  independently extracted tactics and those in `aiir report`. Use
  `aiir report --knowledge-only -k ./knowledge` or
  `aiir report --knowledge-dir ./knowledge` instead.

### Changed
- `server/loader.scan_reports()` now groups by `incident_id`; pre-v0.4.0 reports
  without an `incident_id` are still shown individually (backward-compatible).
- Dashboard stat label changed from "レポート" to "インシデント" to reflect grouping.
- `server/routes.py`: `/report` route accepts `?id=&lang=` in addition to legacy
  `?path=` for backward compatibility.

## [0.4.0] - 2026-03-20

### Added
- **`aiir translate` command**: translate a report JSON into another language while
  preserving technical content (tool names, commands, IOCs, IDs, tags, category slugs).
  Saves translated output as `<stem>.<lang>.json` alongside the source file.
  Supported languages: `ja` (Japanese), `zh` (Simplified Chinese), `ko` (Korean),
  `de` (German), `fr` (French), `es` (Spanish); any BCP-47 code accepted.
  Translation is performed section by section (summary, activity, roles, tactics)
  with 4 focused LLM calls per report.
- `src/aiir/translate/translator.py` — new module with `translate_report()` and
  per-section helpers (`_translate_summary`, `_translate_activity`, `_translate_roles`,
  `_translate_tactics`).
- 12 new tests in `tests/test_translate/test_translator.py` covering field preservation,
  fallback on missing LLM keys, and section-skipping for partial reports.

### Fixed
- **`Relationship.to_user` list coercion**: LLMs sometimes return a list of
  usernames for the `to_user` field (e.g. group relationships). Added
  `field_validator` to join list values into a comma-separated string instead
  of raising a `ValidationError`.

### Changed
- **English output enforced in all analysis prompts**: added
  `IMPORTANT: Always respond in English regardless of the language of the input conversation.`
  to the system prompts of `summarizer.py`, `activity.py`, `roles.py`, and `extractor.py`.
  Prevents LLMs from "helpfully" switching to the input conversation's language
  (common with local 20B-class models and Japanese IR conversations).

## [0.3.0] - 2026-03-20

### Added
- **stail NDJSON format support**: `aiir ingest` now auto-detects newline-delimited
  JSON (one message object per line), the native export format of stail. `channel_name`
  is derived from the file stem; `export_timestamp` from the latest message timestamp.
- **Bot messages included in analysis**: All four analysis modules (summarizer, activity,
  roles, extractor) now include bot-posted messages in the conversation text sent to the
  LLM. Bot posts are prefixed with `[bot]` so the model can distinguish post types.
  This captures automated tool output (EDR alerts, firewall actions, VirusTotal results,
  escalation bots) that was previously invisible to the LLM.
- **LLM response normalization pipeline** (`llm/client.py`):
  - `json_object` mode fallback: catches `BadRequestError` and retries in `text` mode
    for endpoints that only accept `json_schema` or `text` (e.g. LM Studio, many local LLMs).
  - `json-repair` integration: strips markdown code fences (` ```json ` blocks) and
    repairs minor JSON issues that text-mode LLMs sometimes produce.
  - `_strip_reasoning_blocks()`: removes reasoning/thinking blocks before JSON parsing.
    Supports `<think>`, `<thinking>`, `<reasoning>`, `<reflection>`, `<scratchpad>`,
    `<analysis>` (closed and unclosed), Mistral's `[THINK]...[/THINK]`, and
    DeepSeek-R1/Hunyuan's `<answer>...</answer>` (content extracted, not discarded).
    Handles case-insensitive matching and truncated (unclosed) blocks.
- New dependency: `json-repair>=0.58.6`.

### Fixed
- **Model validation robustness**: LLM output variability no longer causes crashes:
  - `Relationship.to_user` is now `Optional[str]` (single-participant incidents may
    return `null` for relationship targets).
  - `Tactic.procedure` and `Tactic.observations` accept list input and join to string.
  - `Action.findings` is now optional (default `""`) and accepts `null` or list input.
- **`.gitignore` scope**: `knowledge/` and `report.*` patterns are now anchored to the
  repository root (`/knowledge/`, `/report.md`, `/report.json`) so they no longer
  shadow `src/aiir/knowledge/` — `formatter.py` and `__init__.py` were previously
  untracked due to this bug.
- **`pyproject.toml`**: removed deprecated `[tool.uv] dev-dependencies` block
  (superseded by `[dependency-groups]`); eliminates uv deprecation warning.
- **Keychain test isolation**: `test_config_uses_keychain_when_env_not_set` now patches
  `get_config()` so a local `.env` file does not interfere with the keychain fallback test.

## [0.2.0] - 2026-03-20

### Added
- **`aiir serve` command**: local read-only web UI for browsing analysis output files.
  Starts a FastAPI server bound to `127.0.0.1` only (security: never binds to 0.0.0.0).
- **Dashboard** (`/`): summary statistics (report count, severity breakdown, tactic count
  by category) with report cards linking to full report views.
- **Report view** (`/report?path=...`): tabbed view of Summary, Activity, Roles, and
  Tactics for a single incident report JSON file.
- **Knowledge library** (`/knowledge`): filterable grid of tactic YAML documents with
  category and tag filters.
- **Tactic detail** (`/tactic?path=...`): full view of a single knowledge tactic including
  purpose, tools, procedure, observations, tags, and source metadata.
- **JSON APIs**: `/api/reports` and `/api/knowledge` for programmatic access.
- `src/aiir/server/` module: `app.py` (FastAPI factory), `routes.py` (route handlers),
  `loader.py` (file scanning with path traversal prevention), `templates/` (Jinja2 HTML).
- New dependencies: `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `jinja2>=3.1`,
  `python-multipart>=0.0.9`, `aiofiles>=23.0`.
- New dev dependency: `httpx>=0.27` (required for FastAPI `TestClient`).
- Test suite: `tests/test_server/test_loader.py` and `tests/test_server/test_routes.py`.

## [0.1.5] - 2026-03-20

### Security
- **Nonce-tagged prompt injection defense**: `sanitize_for_llm()` now generates a
  cryptographically random 64-bit nonce (via `secrets.token_hex(8)`) and embeds it
  in the wrapping tag name: `<user_message_{nonce}>` / `</user_message_{nonce}>`.
  This prevents attackers from predicting the closing tag and breaking out of the
  data boundary with `</user_message>` payloads.
- One nonce is generated per export session (in `aiir ingest`) and shared across
  all messages. The nonce is stored in `ProcessedExport.sanitization_nonce` so
  LLM system prompts can reference the same tag consistently.
- All four analysis modules (`summarizer`, `activity`, `roles`, `extractor`) now
  build their system prompts dynamically via `_build_system_prompt(nonce)` instead
  of using a static `SYSTEM_PROMPT` constant.

### Added
- `generate_nonce()` — public helper in `sanitizer.py`
- `build_data_tag(nonce)` / `build_data_tag_close(nonce)` — helpers for constructing
  nonce-tagged boundary strings in system prompts
- `ProcessedExport.sanitization_nonce` field (defaults to `""` for backward
  compatibility with pre-nonce exports; a fallback nonce is generated at analysis time)
- 16 new tests covering nonce uniqueness, tag embedding, and attacker tag-close resistance

## [0.1.4] - 2026-03-20

### Added
- Bilingual documentation structure: `docs/en/` (English) and `docs/ja/` (Japanese)
- `docs/README.md` — language index table linking both versions of each document
- `docs/en/maintenance.md` — English translation of the maintenance guide
- `docs/ja/` — Japanese translations of all 5 documentation files

### Changed
- `docs/en/knowledge-format.md` — categories table updated to include all Windows/Linux/macOS-specific categories
- All `docs/*.md` files moved into `docs/en/` and `docs/ja/` subdirectories
- `README.md` documentation links updated to reference both language versions

## [0.1.3] - 2026-03-20

### Added
- `docs/maintenance.md` — メンテナンスガイド（依存関係更新・プロンプト変更・カテゴリ追加・セキュリティ・リリース手順・トラブルシューティング）

## [0.1.2] - 2026-03-20

### Added
- **Linux-specific knowledge categories** in tactic extractor:
  `linux-systemd`, `linux-auditd`, `linux-procfs`, `linux-ebpf`, `linux-kernel`
- **Windows-specific knowledge categories** in tactic extractor:
  `windows-event-log`, `windows-registry`, `windows-powershell`,
  `windows-active-directory`, `windows-filesystem`, `windows-defender`
- Platform-specific tool examples in each category description to guide LLM classification
  (Sysmon EventIDs, auditd commands, PowerShell logging artifacts, etc.)
- Windows/Linux IRツール認識ガイドを `CLAUDE.md` に追加

### Changed
- Category list in `extractor.py` restructured into sections:
  Cross-platform / Linux / Windows / macOS for clarity

## [0.1.1] - 2026-03-20

### Added
- **macOS Keychain integration** (`src/aiir/keychain.py`): store LLM API key in macOS
  Keychain (or platform equivalent via `keyring` library) with `aiir config set-key`
- **`aiir config` subgroup**: `set-key`, `delete-key`, `show` subcommands for
  credential and configuration management
- **macOS-specific knowledge categories** in tactic extractor: `macos-unified-logging`,
  `macos-launchd`, `macos-gatekeeper`, `macos-endpoint-security`, `macos-filesystem`
- **`file://` URL defanging**: macOS logs (quarantine events, Gatekeeper blocks, crash
  reports) use `file://` references; scheme is now defanged to `fxxle://`
- Keychain fallback in `config.get_llm_config()`: resolves API key from Keychain when
  `AIIR_LLM_API_KEY` env var is not set
- macOS-specific `.gitignore` entries: `._*` (resource forks), `.AppleDouble`,
  `.LSOverride`, `.Spotlight-V100`, `.Trashes`, `Icon?`

### Changed
- `defang_url()` now handles `file://` scheme (macOS-specific)
- `pyproject.toml`: added `keyring>=25.0` dependency

## [0.1.0] - 2026-03-20

### Added
- Initial project structure with uv/pyproject.toml configuration
- `aiir ingest` command: parse scat/stail JSON exports, defang IoCs, detect prompt injection
- `aiir summarize` command: generate incident summary using LLM
- `aiir activity` command: analyze per-participant activities using LLM
- `aiir roles` command: infer participant roles and relationships using LLM
- `aiir knowledge` command: extract reusable investigation tactics as YAML documents
- `aiir report` command: generate full incident analysis report (Markdown/JSON)
- IoC defanging for IPv4 addresses, URLs (http/https/ftp), email addresses, and file hashes
- Prompt injection detection with 14 detection patterns
- OpenAI-compatible LLM client with configurable endpoint URL, API key, and model
- Pydantic-based configuration via environment variables (`AIIR_LLM_*` prefix)
- Full Pydantic data models for input, preprocessed, and analysis data
- YAML knowledge document formatter with tactic ID generation
- Comprehensive test suite for parser, LLM client, and knowledge formatter modules
- Security-first design: no external transmission except configured LLM endpoint
- Documentation: architecture, data format, knowledge format, security considerations

[Unreleased]: https://github.com/magifd2/ai-ir/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/magifd2/ai-ir/releases/tag/v0.1.0
