# ai-ir Maintenance Guide

This document describes procedures for maintaining and improving the ai-ir toolset.

---

## Table of Contents

1. [Routine Maintenance](#1-routine-maintenance)
2. [Dependency Management](#2-dependency-management)
3. [Prompt Maintenance](#3-prompt-maintenance)
4. [Adding and Changing Knowledge Categories](#4-adding-and-changing-knowledge-categories)
5. [Security Maintenance](#5-security-maintenance)
6. [Adding New Features](#6-adding-new-features)
6.4. [Knowledge Extraction via `aiir report`](#64-knowledge-extraction-via-aiir-report)
6.4.1. [Exporting Tactics as Markdown for RAG](#641-exporting-tactics-as-markdown-for-rag)
6.5. [Web UI (`aiir serve`)](#65-web-ui-aiir-serve)
6.6. [Translation (`aiir translate`)](#66-translation-aiir-translate)
6.7. [Process Review (`aiir review`)](#67-process-review-aiir-review)
7. [Test Strategy](#7-test-strategy)
8. [LLM Compatibility](#8-llm-compatibility)
9. [Release Procedure](#9-release-procedure)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Routine Maintenance

### Running Tests

```bash
# All tests (recommended: always run before and after changes)
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=src/aiir --cov-report=term-missing

# Specific module only
uv run pytest tests/test_parser/ -v
uv run pytest tests/test_knowledge/ -v
```

### Checking Configuration

```bash
# Show current configuration (API key is masked)
aiir config show
```

---

## 2. Dependency Management

### Regular Updates (Recommended Monthly)

```bash
# Update uv.lock to latest
uv lock --upgrade

# Install updated dependencies
uv sync

# Verify no regressions with tests
uv run pytest tests/ -v
```

### Security Vulnerability Scanning

```bash
# Scan for known vulnerabilities with pip-audit (install first if needed)
uv add --dev pip-audit
uv run pip-audit
```

If vulnerabilities are found, raise the minimum version bound for the affected package
in `pyproject.toml` and update with `uv lock --upgrade-package <package-name>`.

### Adding Dependencies

```bash
# Production dependency
uv add <package>

# Development only
uv add --dev <package>

# Confirm both pyproject.toml and uv.lock are updated
git diff pyproject.toml uv.lock
```

---

## 3. Prompt Maintenance

Prompts are implemented as `_build_system_prompt(nonce: str) -> str` functions in each
analysis module (not as static constants — the nonce must be embedded at call time).

| File | Responsibility |
|---|---|
| `src/aiir/analyze/summarizer.py` | Incident summary generation |
| `src/aiir/analyze/activity.py` | Participant activity analysis |
| `src/aiir/analyze/roles.py` | Role and relationship inference |
| `src/aiir/knowledge/extractor.py` | Tactic knowledge extraction |
| `src/aiir/analyze/reviewer.py` | IR process quality review (no nonce required — no user text in prompt) |

### Checklist for Changing Prompts

1. **Run tests before making changes** to record the current state
2. **Always preserve the security guards** (the following two elements must not be removed or weakened):
   - Wrapping data in `<user_message_{nonce}>` nonce-tagged blocks
   - Explicitly stating that content within the tags is data, not instructions
3. **If the JSON schema changes**, also update the corresponding model in `src/aiir/models.py`
4. **Record the change in CHANGELOG.md**

### Impact Scope of Prompt Changes

```
Changing _build_system_prompt()
    ├─ JSON schema changed    → also update models in models.py
    ├─ Output fields added    → also update Markdown formatter
    └─ Categories changed     → also update tests in test_extractor_prompt.py
```

### Verifying Prompt Behavior

Example script to validate prompts against the actual LLM:

```bash
# Try summarize with sample data
aiir summarize tests/fixtures/sample_export.json
```

It is also recommended to visually inspect the output of `aiir ingest` before
sending it to the production LLM.

---

## 4. Adding and Changing Knowledge Categories

### Steps to Add a New Category

**Step 1** — Add the category to `SYSTEM_PROMPT` in `src/aiir/knowledge/extractor.py`

```python
# Example: adding a new Linux category
- linux-newcategory: Brief description of target tools or techniques — `tool1`, `tool2`
```

Formatting principles:
- Category names use kebab-case (`platform-concept`)
- Include representative tool names and commands in the description (helps the LLM classify correctly)
- Platform-specific categories should have `linux-`/`windows-`/`macos-` prefixes

**Step 2** — Add tests to `tests/test_knowledge/test_extractor_prompt.py`

```python
@pytest.mark.parametrize("category", [
    ...,
    "linux-newcategory",  # ← add here
])
def test_linux_category_present(category):
    assert category in SYSTEM_PROMPT
```

Also add tests for representative tool names:

```python
@pytest.mark.parametrize("tool", [
    ...,
    "tool1",  # ← add here
])
def test_linux_tool_mentioned(tool):
    assert tool in SYSTEM_PROMPT
```

**Step 3** — Update the category table in `docs/en/knowledge-format.md` (and `docs/ja/knowledge-format.md`)

**Step 4** — Add an entry to `CHANGELOG.md` and commit

### Removing or Merging Categories

Removing an existing category breaks consistency with previously generated YAML knowledge
documents. Prefer **merging into `other`** or **expanding the category description** over
deletion.

If deletion is unavoidable:
1. Determine the target category for migration
2. Bulk-replace existing YAML files (`sed -i` or a Python script)
3. Update tests accordingly

---

## 5. Security Maintenance

### Extending IoC Defang Patterns

If a new IoC type is needed (e.g., IPv6, Bitcoin addresses), edit
`src/aiir/parser/defang.py`.

Required steps when adding:
- Add regex tests to `tests/test_parser/test_defang.py`
- Verify both false positives (over-matching) and false negatives (misses)
- Ensure no overlap with existing IoC processing (the `_overlaps()` function guards this)

```python
# Example: adding a new pattern (defang.py)
_NEW_PATTERN = re.compile(r"...", re.IGNORECASE)

# Add at the appropriate priority position within defang_text()
for m in _NEW_PATTERN.finditer(text):
    if _overlaps(m.start(), m.end(), replacements):
        continue
    ...
```

### Extending Prompt Injection Detection Patterns

If a new attack pattern is discovered, append it to the `INJECTION_PATTERNS` list
in `src/aiir/parser/sanitizer.py`.

```python
INJECTION_PATTERNS = [
    ...
    r"new_pattern",  # Add a comment explaining how/where this was found
]
```

Don't forget to add corresponding tests to `tests/test_parser/test_sanitizer.py`.

### API Key Rotation

```bash
# If stored in Keychain
aiir config delete-key
aiir config set-key   # enter the new key

# If managed via environment variable
export AIIR_LLM_API_KEY=<new-key>
# or edit the .env file
```

If a credential leak occurred during incident response, rotate the API key used for
the analysis promptly (see also the recommendations in `docs/en/security.md`).

---

## 6. Adding New Features

### Adding a New Analysis Subcommand

Perform the following in order:

1. **`src/aiir/models.py`** — Add input/output data models (Pydantic)
2. **`src/aiir/analyze/<name>.py`** — Implement analysis logic and `SYSTEM_PROMPT`
3. **`src/aiir/cli.py`** — Register the subcommand with `@main.command()`
4. **`tests/test_analyze/test_<name>.py`** — Write tests with the LLM client mocked
5. **`CHANGELOG.md`** — Document the addition
6. **`README.md`** — Add usage examples

### Supporting a New Input Format

Currently only the scat/stail JSON export format is supported. To support a new format
(e.g., Splunk export):

1. Define a new model (e.g., `SplunkExport`) in `src/aiir/models.py`
2. Add a corresponding loader function to `src/aiir/parser/loader.py`
3. Add format detection logic to `_load_or_preprocess()` in `src/aiir/cli.py`
4. Add sample files to `tests/fixtures/` and write tests

---

## 6.4. Report Generation (`report/generator.py`)

### Design Rationale: Two Markdown Renderers

Each analysis module (`summarizer`, `activity`, `roles`) exposes a `format_*_markdown()`
function that renders a **standalone** Markdown document with H2 top-level headings, suitable
for piping to a renderer or saving on its own.

`generate_markdown_report()` in `report/generator.py` renders a **combined** report where
those same sections appear as H3 sub-sections under H2 headers. The rendering details also
differ intentionally:

| Aspect | Standalone (`format_*_markdown`) | Combined (`generate_markdown_report`) |
|---|---|---|
| Activity heading level | H2 (`## @name`) | H3 (`### @name`) |
| Roles confidence label | `[HIGH]` / `[MED]` / `[LOW]` | `(High confidence)` etc. |
| Roles participant layout | H3 heading + `**Evidence:**` block | bullet list with `_evidence_` sub-bullets |
| Relationships table | 4 columns incl. Description | 3 columns (Description omitted) |

These are two distinct rendering contexts with different heading hierarchy and information
density requirements. Do not refactor them into a shared implementation without accounting
for these structural and stylistic differences.

### Knowledge Extraction via `aiir report`

The standalone `aiir knowledge` command was removed in v0.5.0 to prevent inconsistency
between the knowledge base and reports (they previously made independent LLM calls and
could return different numbers of tactics).

Use `aiir report` instead:

```bash
# Full report + save tactics as YAML in one command (recommended)
aiir report preprocessed.json --format json -o report.json --knowledge-dir ./knowledge

# Tactics only (skip summary / activity / roles)
aiir report preprocessed.json --knowledge-only --knowledge-dir ./knowledge
```

Because `--knowledge-dir` shares the same LLM call as the report, the number of tactics
in `report.json` and in the YAML files is always identical.

### Exporting Tactics as Markdown for RAG

Use `aiir knowledge export` to convert existing tactic YAML files into individual Markdown
documents suitable for ingestion into a RAG knowledge base (e.g.
[lite-rag](https://github.com/nlink-jp/lite-rag)).

```bash
# Convert all tac-*.yaml files in ./knowledge to ./knowledge-md/*.md
aiir knowledge export -k ./knowledge -o ./knowledge-md

# Default output dir is <knowledge-dir>-md (i.e. ./knowledge-md)
aiir knowledge export -k ./knowledge
```

**Why one file per tactic?** Keeping each RAG document to a single tactic prevents retrieval
results from being dominated by neighbouring tactics in a combined file. Each document is
semantically focused and independently retrievable.

**Markdown structure per file:**

```
# {title}

**ID:** ... | **Category:** ... | **Confidence:** ...
**Tags:** ...
**Source:** ...

## Purpose
## Tools
## Procedure
## Observations
## Evidence   ← only present when evidence field is non-empty
```

### Design Rationale: Sequential LLM Calls in `aiir report`

`aiir report` makes four LLM calls sequentially (summary → activity → roles → tactics).
This is intentional for the primary deployment target.

**Why:** The primary target is a local [Ollama](https://ollama.com/) instance running on a
single GPU. Ollama serialises requests to the GPU regardless of how many threads submit them
concurrently — parallel HTTP calls simply queue at the GPU and produce no speedup. We measured
this: `translate_report` (4 concurrent calls) improved from 103.7 s to 78.9 s (1.31×), far
below the theoretical maximum because the GPU was the bottleneck, not the HTTP transport.

`translate_report` and `translate_review` **are** parallelised, because the four translation
sections are independent and the pattern holds: they translate distinct parts of the same
document with no shared state.

**For cloud API users** (OpenAI, Anthropic), concurrent analysis calls would yield a 3–4×
speedup. This can be revisited if cloud deployment becomes a primary use case and users report
total report generation time as a pain point.

---

## 6.5. Web UI (`aiir serve`)

The `aiir serve` command starts a read-only local web server for browsing reports and
knowledge documents.

### Usage

```bash
# Scan current directory, serve on port 8765, auto-open browser
aiir serve

# Specify data directory and port
aiir serve /path/to/analysis --port 9000

# Start without opening browser
aiir serve --no-browser
```

### Security

The server **always binds to `127.0.0.1`** (localhost only) and cannot be reached
from the network. Path traversal attacks are prevented: all file paths are resolved
and verified to remain within the data directory before being read.

### File Discovery

The server recursively scans the data directory for:
- **Report JSON files** — identified by having both `"summary"` and `"tactics"` keys
- **Tactic YAML files** — identified by an `id` field starting with `"tac-"`

### Design Rationale: Per-Request Directory Scan (No Cache)

`routes.py` calls `scan_reports()` and `scan_tactics()` on every dashboard request rather than
caching the results. This is intentional.

**Why:** `aiir serve` is a local read-only tool used by a single analyst. The typical workflow
is to run `aiir report` or `aiir review` in one terminal while the server is running in another.
A cached scan would show stale results until the cache expired or was manually invalidated.
Re-scanning on every request guarantees the dashboard always reflects the current filesystem
state with no extra steps.

**Performance:** Scanning dozens of JSON/YAML files on a local SSD takes single-digit
milliseconds — well below the perceptible latency threshold for an interactive tool with no
concurrent users.

**When to reconsider:** If a user reports noticeable page-load latency with a specific dataset
size, the correct solution would be filesystem watching (e.g. `watchfiles`) rather than
time-based expiry caching, as watching avoids staleness entirely.

### Adding a New Page to the Web UI

1. Add a route handler in `src/aiir/server/routes.py`
2. Create a Jinja2 template in `src/aiir/server/templates/`
3. Add the route to the FastAPI app in `src/aiir/server/app.py` if needed
4. Write tests in `tests/test_server/test_routes.py`

### Troubleshooting the Web UI

| Symptom | Likely cause | Fix |
|---|---|---|
| No reports shown | Reports not in expected JSON format | Run `aiir report` first; check file has `summary`+`tactics` keys |
| No tactics shown | YAML id field missing `tac-` prefix | Check formatter output; re-run `aiir report --knowledge-only -k ./knowledge` |
| Port already in use | Another process on port 8765 | Use `--port <other>` |

---

## 6.6. Translation (`aiir translate`)

The `aiir translate` command takes a report JSON (produced by `aiir report --format json`)
and produces a localized copy with narrative fields translated into the target language.
Technical content is preserved in English.

### Usage

```bash
# Translate to Japanese — output defaults to report.ja.json
aiir translate report.json --lang ja

# Explicit output path
aiir translate report.json --lang zh -o report.zh.json
```

### Translated vs. Preserved Fields

| Field | Translated |
|---|---|
| `summary.title`, `root_cause`, `resolution`, `summary` | Yes |
| `summary.timeline[].event` | Yes |
| `activity.participants[].role_hint` | Yes |
| `activity.participants[].actions[].purpose`, `findings` | Yes |
| `roles.participants[].inferred_role`, `evidence` | Yes |
| `roles.relationships[].description` | Yes |
| `tactics[].title`, `purpose`, `procedure`, `observations` | Yes |
| `activity.actions[].method` (commands) | **No** |
| `tactics[].tools`, `tags`, `category`, `id` | **No** |
| Backtick-wrapped code in any field | **No** |
| IOCs, usernames, channel names, timestamps | **No** |

### Design Notes

- **Analysis is always in English**: All analysis system prompts include
  `IMPORTANT: Always respond in English regardless of the language of the input conversation.`
  This prevents local LLMs from "helpfully" switching to the conversation's language.
- **Translation is a separate step**: The English source JSON is kept as the authoritative
  record; translations are supplementary output.
- **LLM calls**: 4 calls per report (summary, activity, roles, tactics), each focused on
  one section to keep context short and reduce truncation risk.
- **Fallback safety**: If the LLM omits a field in the translated JSON, the original
  English value is preserved. Translation failure never corrupts the report.

### Supported Languages (built-in names)

| Code | Language |
|---|---|
| `ja` | Japanese |
| `zh` | Simplified Chinese |
| `ko` | Korean |
| `de` | German |
| `fr` | French |
| `es` | Spanish |

Any BCP-47 code can be used; the code is passed directly to the LLM as the target language
name for unlisted languages.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Some fields not translated | LLM treats technical-looking text as code | Acceptable — tool names and commands should remain in English |
| JSON parse error | LLM returned malformed JSON | `json-repair` handles most cases; retry or use a more capable model |
| Input file rejected | File missing `summary` or `tactics` keys | Run `aiir report --format json` first to generate a valid report |

---

## 6.7. Process Review (`aiir review`)

The `aiir review` command analyzes a completed report JSON and evaluates the quality
of the incident response *process* — not the technical content of the incident itself.

### Usage

```bash
# Analyze process quality — outputs report.review.json alongside the source report
aiir review report.json

# Markdown output (for reading or sharing)
aiir review report.json --format markdown -o review.md
```

### What It Evaluates

| Dimension | Description |
|---|---|
| Phase timing | Estimated duration and quality rating for each IR phase (detection / initial response / containment / resolution) |
| Communication quality | Information-sharing delays and silos observed |
| Role clarity | IC identification, role gaps and overlaps |
| Tool appropriateness | Whether the right tools and methods were used |
| Strengths | Concrete things the team did well |
| Improvements | Specific, actionable suggestions for next time |
| Next-incident checklist | Prioritised preparation items (high / medium / low) |

### Output File Convention

By default, `aiir review report.json` writes `report.review.json` alongside the source
file. The web dashboard (`aiir serve`) automatically detects this file and shows a
**対応評価** tab in the report detail view. Translated report variants (e.g.
`report.ja.json`) also resolve to the same `report.review.json`.

### Design Notes

- **No raw message re-transmission**: `reviewer.py` uses only the already-structured
  sections of the report (summary / activity / roles / tactics) as LLM input. Raw
  Slack message text is never re-sent. This reduces token consumption and eliminates
  prompt injection risk for this step.
- **No nonce required**: Because user-sourced text is not included in the prompt,
  nonce-tagged XML safety wrapping is not needed.
- **English output enforced**: The system prompt includes the same
  `IMPORTANT: Always respond in English…` instruction as the other analysis modules.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 対応評価 tab not shown | `report.review.json` not found | Run `aiir review report.json` first |
| Very short/generic output | Report has little activity or role data | Run full `aiir report` pipeline before reviewing |
| JSON parse error | LLM returned malformed JSON | Retry or switch to a more capable model |

---

## 7. Test Strategy


### Test Types and Responsibilities

| Test Type | Location | What it tests |
|---|---|---|
| Unit tests | `tests/test_parser/` | Direct input/output verification of defang and sanitizer |
| Prompt content tests | `tests/test_knowledge/test_extractor_prompt.py` | Whether categories and tool names exist in `_build_system_prompt()` output |
| Mock integration tests | `tests/test_llm/` | API call format of the LLM client |
| Formatter tests | `tests/test_knowledge/test_formatter.py` | Structure of YAML output |
| Keychain tests | `tests/test_keychain/` | Behavior verification with an in-memory mock keyring |
| Server tests | `tests/test_server/` | FastAPI route responses and path traversal prevention |

### Testing Policy for LLM-Dependent Features

Do **not** write tests that make real calls to the LLM (OpenAI API). Reasons:

- Incurs cost
- Non-deterministic responses make CI unstable
- Rate limits can be hit

Instead, use `unittest.mock.patch` to mock the `OpenAI` class and verify that the
client calls the API with the correct parameters (`model`, `messages`, `response_format`).
Correctness of the analysis logic is ensured by prompt content tests and manual verification.

### Testing Principles

- Follow the **Arrange / Act / Assert** three-part structure
- Recommended test name format: `test_<subject>_<condition>_<expected_result>`
- Use `pytest.mark.parametrize` actively to cover boundary values, normal values, and error cases
- Each test function should verify exactly one thing

### Test Scope Boundaries

**Third-party library internals are out of scope.** We test our integration with a library, not
the library's own behaviour. For example:
- `json_repair`: We verify that `complete_json()` returns valid JSON for various LLM response
  formats (reasoning tags, markdown fences). We do not test `repair_json()` directly — that
  is the library's own responsibility.
- External validators (Pydantic): We test that our models accept and reject the inputs we care
  about. We do not test Pydantic's type coercion logic itself.

**Implicit coverage is acceptable when artificial tests would be fragile.** If a function is
already exercised by higher-level tests that use realistic inputs, adding an isolated test for
one narrow internal behaviour has diminishing returns — especially if it would need to be
updated every time the implementation changes for unrelated reasons. The `_overlaps()` guard
in `defang.py` is one example: it is exercised by the existing defang tests on realistic
multi-IoC inputs, and a test that constructs an artificial overlap would be tightly coupled to
the current regex implementation without adding meaningful new coverage.

The guiding question is: **"If this code had a bug, would the existing tests catch it?"**
If yes, a new test adds maintenance overhead without safety benefit.

---

## 8. LLM Compatibility

### Response Normalization Pipeline

`llm/client.py` normalizes LLM output before returning it to callers:

```
raw response
  │
  ├─ _strip_reasoning_blocks()   remove <think>, <thinking>, <reasoning>,
  │                               <reflection>, <scratchpad>, <analysis>,
  │                               [THINK]...[/THINK], extract <answer>...</answer>
  │
  └─ repair_json()               strip markdown code fences, repair minor JSON
```

This pipeline runs automatically in `complete_json()` for all models.

### Supported Response Format Modes

| Mode | Trigger | Notes |
|---|---|---|
| `json_object` | Default (OpenAI, most APIs) | Guarantees valid JSON output |
| `text` fallback | `BadRequestError` on first attempt | Used by LM Studio, some local LLMs |

### Adding Support for a New Reasoning Tag

If a new model emits a reasoning block in an unseen tag format:

1. Add the tag name to `_REASONING_TAGS` in `src/aiir/llm/client.py`
2. Add a parametrized test case in `tests/test_llm/test_client.py`

For square-bracket formats (like Mistral `[THINK]`), add a new regex constant
and call `.sub()` inside `_strip_reasoning_blocks()`.

### Supported Input Formats

| Format | Detection | Source |
|---|---|---|
| Single JSON object | `json.loads()` succeeds | scat export |
| NDJSON (one object per line) | `json.loads()` raises "Extra data" | stail export |

---

## 9. Release Procedure

### Version Numbering Policy

Follows [Semantic Versioning](https://semver.org/):

| Type of Change | Version |
|---|---|
| Security fix, bug fix | PATCH (x.y.**Z**) |
| New category, prompt improvement, new subcommand | MINOR (x.**Y**.0) |
| Breaking data model change, CLI interface change | MAJOR (**X**.0.0) |

### Release Steps

```bash
# 1. Confirm all tests pass
uv run pytest tests/ -v

# 2. Update version in src/aiir/__init__.py
#    __version__ = "x.y.z"

# 3. Update version in pyproject.toml
#    version = "x.y.z"

# 4. Change [Unreleased] to [x.y.z] - YYYY-MM-DD in CHANGELOG.md,
#    and add a new [Unreleased] section at the top

# 5. Commit
git add src/aiir/__init__.py pyproject.toml CHANGELOG.md
git commit -m "chore: release v x.y.z"

# 6. Tag
git tag vx.y.z
```

### CHANGELOG Format

```markdown
## [x.y.z] - YYYY-MM-DD

### Added
- Description of new feature

### Changed
- Description of change (prefix breaking changes with "**Breaking:**")

### Fixed
- Description of bug fix

### Security
- Description of security fix
```

---

## 10. Troubleshooting

### `AIIR_LLM_API_KEY is not configured` Error

```bash
# Check current configuration
aiir config show

# Set via environment variable
export AIIR_LLM_API_KEY=<your-key>

# Or store in Keychain
aiir config set-key
```

### LLM Returns No JSON / JSON Parse Error

`complete_json()` specifies `response_format={"type": "json_object"}`, but some models
and self-hosted models may ignore this mode.

Solutions:
1. Verify the model supports JSON mode
2. Change `AIIR_LLM_MODEL` to try a different model
3. Check whether the LLM response is valid JSON using `--debug` logs

### Large Number of Injection Risk Warnings from `ingest`

IR conversations often contain attacker commands and pseudo-instructions, making false
positives common. You can reduce false positives by adjusting `INJECTION_PATTERNS` in
`src/aiir/parser/sanitizer.py`.

Confirm that existing tests still pass after any changes.

### `uv sync` Fails in a Sandbox Environment

```bash
# Re-run with a writable cache directory
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

### Tests Suddenly Fail (Prompt Tests)

`test_extractor_prompt.py` verifies that category names and tool names are present in
the prompt string. If tests fail after editing the prompt:

1. Identify the category names or tool names that were removed or changed
2. Update the tests accordingly, or reconsider the prompt changes
3. Check whether the removed category is used in any existing YAML knowledge documents
