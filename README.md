# ai-ir: AI-powered Incident Response Analysis Toolset

`ai-ir` analyzes incident response Slack conversation history exported via
[scat](https://github.com/magifd2/scat) or [stail](https://github.com/magifd2/stail)
to generate actionable reports and reusable knowledge.

## Features

- **Incident Summary** — AI-generated timeline, root cause, and executive summary
- **Activity Analysis** — Per-participant breakdown of methods, tools, and findings
- **Role Inference** — Infer IR roles (Incident Commander, SME, etc.) and relationships
- **Knowledge Extraction** — Extract reusable investigation tactics as YAML documents; export to Markdown for RAG ingestion
- **Process Review** — Evaluate IR process quality (phase timing, communication, role clarity, improvement checklist)
- **Translation** — Translate report JSON into another language while preserving technical content
- **Local Web UI** — Browse analysis output with `aiir serve` (read-only, localhost only)
- **Security-first** — IoC defanging and prompt injection defense built-in

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/magifd2/ai-ir
cd ai-ir
uv sync
```

## Configuration

Copy `.env.example` to `.env` and configure your LLM endpoint:

```bash
cp .env.example .env
# Edit .env with your settings
```

```bash
AIIR_LLM_BASE_URL=https://api.openai.com/v1
AIIR_LLM_API_KEY=sk-...
AIIR_LLM_MODEL=gpt-4o
```

Environment variables can also be set directly without a `.env` file.

## Usage

### Export Slack channel history

```bash
# Using stail
stail export -c "#incident-response" --output incident.json

# Using scat
scat export log --channel "#incident-response" --output incident.json
```

### Step 1: Ingest and preprocess

Parse the export, defang IoCs, and detect prompt injection risks:

```bash
uv run aiir ingest incident.json -o incident.preprocessed.json
```

Output goes to stdout by default (pipe-friendly):

```bash
uv run aiir ingest incident.json | uv run aiir summarize -
```

### Step 2: Generate analysis

Each analysis command accepts either raw export files or preprocessed files:

```bash
# Generate incident summary (Markdown)
uv run aiir summarize incident.json

# Generate incident summary (JSON)
uv run aiir summarize incident.json --format json -o summary.json

# Analyze per-participant activities
uv run aiir activity incident.json -o activity.md

# Infer participant roles and relationships
uv run aiir roles incident.json -o roles.md

# Generate full report (JSON) and save tactics as YAML knowledge docs simultaneously
uv run aiir report incident.json --format json -o report.json -k ./knowledge/

# Generate full report (Markdown)
uv run aiir report incident.json -o report.md

# Extract tactics only (no full report)
uv run aiir report incident.json --knowledge-only -k ./knowledge/
```

### Full pipeline example

```bash
# Preprocess once, then run all analyses
uv run aiir ingest incident.json -o preprocessed.json

uv run aiir summarize preprocessed.json -o summary.md
uv run aiir activity preprocessed.json -o activity.md
uv run aiir roles preprocessed.json -o roles.md

# Full report + knowledge docs in one step
uv run aiir report preprocessed.json --format json -o report.json -k ./knowledge/
```

### Step 3: Translate the report (optional)

Analysis is always performed in English for maximum accuracy. Use `aiir translate` to
produce a localized version of the report JSON. Technical content (tool names, commands,
IOCs, IDs, tags) is preserved in English.

```bash
# Translate to Japanese — saves report.ja.json alongside report.json
uv run aiir translate report.json --lang ja

# Supported language codes: ja, zh, ko, de, fr, es
# Any BCP-47 code is accepted for languages not in the built-in list
uv run aiir translate report.json --lang zh -o report.zh.json
```

### Step 4: Review the response process (optional)

After generating the report, analyze the quality of *how the team responded* — phase
timing, communication quality, role clarity, and concrete improvement suggestions:

```bash
# Saves report.review.json alongside report.json
uv run aiir review report.json

# Markdown output for sharing
uv run aiir review report.json --format markdown -o review.md
```

The web UI automatically shows a **対応評価** tab when `report.review.json` is present.

### Export tactics as Markdown for RAG (optional)

Convert tactic YAML files to individual Markdown documents for ingestion into a RAG knowledge base.
One file per tactic keeps retrieval focused and precise.

```bash
# Convert all tactic YAMLs in ./knowledge to Markdown in ./knowledge-md
uv run aiir knowledge export -k ./knowledge -o ./knowledge-md
```

### Browse results in the web UI

After generating reports and knowledge documents, launch the local web UI:

```bash
# Serve current directory (scans recursively for report JSON and tactic YAML files)
uv run aiir serve

# Serve a specific directory on a custom port
uv run aiir serve ./output --port 9000

# Start without opening a browser tab automatically
uv run aiir serve --no-browser
```

The server binds to `127.0.0.1` only and is read-only. Open http://localhost:8765
in your browser to view the dashboard.

## Security

- **No external transmission**: Only the configured LLM endpoint receives data
- **IoC defanging**: IPv4 addresses, URLs, domains, emails, and hashes are defanged before LLM transmission
- **Prompt injection defense**: All Slack message text is wrapped in XML tags and scanned for injection patterns
- **Local processing**: All parsing and preprocessing runs locally

See [docs/en/security.md](docs/en/security.md) for detailed security considerations.

## Documentation

- [Architecture](docs/en/architecture.md) / [アーキテクチャ](docs/ja/architecture.md)
- [Data Format](docs/en/data-format.md) / [データフォーマット](docs/ja/data-format.md)
- [Knowledge Format](docs/en/knowledge-format.md) / [ナレッジフォーマット](docs/ja/knowledge-format.md)
- [Security](docs/en/security.md) / [セキュリティ](docs/ja/security.md)
- [Maintenance](docs/en/maintenance.md) / [メンテナンス](docs/ja/maintenance.md)

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=aiir --cov-report=term-missing
```

## License

MIT License
