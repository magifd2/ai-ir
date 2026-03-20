# ai-ir Project Rules

## Purpose
Incident response Slack conversation analysis toolset. Analyzes scat/stail JSON export files
to generate incident summaries, participant activity analysis, role inference, and reusable
investigation tactic knowledge documents.

## Architecture

### Toolset Components
- `aiir ingest` - Parse, defang IoCs, sanitize prompt injection risks → outputs preprocessed JSON
- `aiir summarize` - Generate incident summary using LLM
- `aiir activity` - Analyze per-participant activities using LLM
- `aiir roles` - Infer participant roles and relationships using LLM
- `aiir report` - Generate full analysis report; optionally save tactics as YAML (`--knowledge-dir`); tactics-only mode (`--knowledge-only`)
- `aiir translate` - Translate report JSON into another language (narrative fields only)
- `aiir serve` - Start read-only local web UI (FastAPI, binds to 127.0.0.1 only)

### Module Structure
```
src/aiir/
  cli.py           - Click-based CLI entry point
  config.py        - Pydantic-settings based configuration
  models.py        - All Pydantic data models
  parser/
    loader.py      - scat/stail JSON export loader
    defang.py      - IoC defanging and extraction
    sanitizer.py   - Prompt injection detection/sanitization
  llm/
    client.py      - OpenAI-compatible LLM client
  analyze/
    summarizer.py  - Incident summary generation
    activity.py    - Participant activity analysis
    roles.py       - Role and relationship inference
  knowledge/
    extractor.py   - Tactic knowledge extraction
    formatter.py   - YAML knowledge document formatter
  report/
    generator.py   - Full report generation; make_incident_id() for grouping
  server/
    app.py         - FastAPI application factory (create_app)
    routes.py      - Route handlers (dashboard, report, knowledge, tactic, API)
    loader.py      - File scanning, incident_id grouping, path traversal prevention
    templates/     - Jinja2 HTML templates (Tailwind CSS CDN, Japanese UI)
  translate/
    translator.py  - translate_report(): narrative field translation via LLM
```

## Security Rules

1. **No external transmission**: Only the configured LLM endpoint may receive data.
   No analytics, telemetry, or third-party API calls are permitted.
2. **Prompt injection defense**: ALL user-sourced text (Slack messages) MUST be processed
   through `sanitizer.sanitize_for_llm()` before inclusion in LLM prompts.
3. **IoC defanging**: ALL IoCs in Slack messages MUST be defanged via `defang.defang_text()`
   before storage or transmission. This prevents accidental activation of malicious URLs/IPs.
4. **No secret logging**: API keys, tokens, and credentials must never appear in logs or output.
5. **Input validation**: All input files are validated against Pydantic models before processing.

## Development Rules

- Small, focused modules — each file has a single clear responsibility
- Tests implemented alongside code in `tests/` directory
- All public functions must have docstrings
- Type hints required for all function signatures
- CHANGELOG.md updated on each feature addition
- No hardcoded credentials or endpoints
- Python with uv virtual environment (`uv sync` to install dependencies)
- Run tests: `uv run pytest tests/ -v`

## LLM Configuration

Configure via environment variables (or `.env` file):

```bash
AIIR_LLM_BASE_URL=https://api.openai.com/v1   # OpenAI-compatible endpoint
AIIR_LLM_API_KEY=sk-...                         # API key
AIIR_LLM_MODEL=gpt-4o                           # Model name
```

The LLM client uses the OpenAI Python SDK with configurable `base_url`, enabling
use with any OpenAI-compatible API (OpenAI, Azure, local Ollama, etc.).

## Knowledge Format

Tactic knowledge documents are YAML files with this structure:

```yaml
id: "tac-20260319-001"
title: "Descriptive tactic title"
purpose: "What question/problem this tactic helps answer"
category: "log-analysis"
tools:
  - command_or_tool_name
procedure: |
  Step-by-step procedure description
observations: |
  How to interpret results, what patterns mean
tags:
  - tag1
source:
  channel: "#channel-name"
  participants:
    - username
created_at: "2026-03-19"
```

### Cross-platform / General
`log-analysis`, `network-analysis`, `process-analysis`, `memory-forensics`,
`database-analysis`, `container-analysis`, `cloud-analysis`, `malware-analysis`,
`authentication-analysis`

### Linux-specific
| Category | Scope |
|---|---|
| `linux-systemd` | journalctl, unit files, systemctl, service timers |
| `linux-auditd` | ausearch, aureport, auditctl, /var/log/audit/ |
| `linux-procfs` | /proc/PID/maps, /proc/PID/fd, /proc/net/ |
| `linux-ebpf` | execsnoop, opensnoop, tcpconnect, bpftool, bcc toolkit |
| `linux-kernel` | dmesg, lsmod, modinfo, OOM killer events |

### Windows-specific
| Category | Scope |
|---|---|
| `windows-event-log` | wevtutil, Get-WinEvent, Event Viewer, Sysmon event IDs |
| `windows-registry` | reg query, Autoruns, Run/RunOnce keys, hive analysis |
| `windows-powershell` | Script Block Logging, transcripts, $PROFILE, PSReadLine history |
| `windows-active-directory` | Get-ADUser, LDAP, GPO, LAPS, DCSync detection |
| `windows-filesystem` | ADS, VSS/vssadmin, MFT, prefetch, LNK/JumpList |
| `windows-defender` | Defender logs, quarantine, exclusion inspection, MpCmdRun.exe |

### macOS-specific
| Category | Scope |
|---|---|
| `macos-unified-logging` | log show / log stream (Apple ULS) |
| `macos-launchd` | launchctl, LaunchAgents/Daemons, plist analysis |
| `macos-gatekeeper` | spctl, codesign, quarantine xattrs |
| `macos-endpoint-security` | TCC database, SIP, ESF events |
| `macos-filesystem` | APFS snapshots, Time Machine, xattr, fs_usage |

`other` — does not fit any category above

## Linux-Specific Notes

### Linux IRツール認識（会話中に出現したら対応カテゴリへ分類）
- **systemd/journald**: `journalctl -u`, `systemctl status`, `journalctl --since`
- **auditd**: `ausearch -m execve`, `aureport -f`, `/var/log/audit/audit.log`
- **プロセス/ファイル**: `ss -tlnp`, `lsof -i`, `lsattr`, `chattr +i`
- **eBPF/BCC**: `execsnoop-bpfcc`, `opensnoop-bpfcc`, `bpftool prog list`, `perf`
- **カーネル**: `dmesg | grep -i oom`, `lsmod`, `modinfo`, `/proc/kallsyms`
- **パッケージ整合性**: `rpm -Va`, `dpkg -V`, `debsums`

## Windows-Specific Notes

### Windows IRツール認識（会話中に出現したら対応カテゴリへ分類）
- **イベントログ**: `wevtutil qe Security`, `Get-WinEvent -LogName Security`, `.evtx`ファイル
- **Sysmon EventID**: 1=ProcessCreate, 3=NetworkConnect, 7=ImageLoad, 11=FileCreate, 13=RegistrySet, 22=DNSQuery
- **レジストリ**: `reg query HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`, Autoruns.exe
- **PowerShell**: PSReadLine履歴, Script Block Log (EventID 4104), モジュールログ (EventID 4103)
- **Active Directory**: `Get-ADUser -Filter`, `Get-ADComputer`, `nltest /dclist`, DCSync痕跡
- **NTFS/VSS**: `Get-Item -Stream *` (ADS確認), `vssadmin list shadows`, prefetch (`C:\Windows\Prefetch\`)
- **Defender**: `Get-MpThreatDetection`, `MpCmdRun.exe -Scan`, Quarantineフォルダ調査

## macOS-Specific Notes

### API Key Storage (Keychain)
- Use `aiir config set-key` to store the LLM API key in macOS Keychain (login keychain).
- Key resolution order: `AIIR_LLM_API_KEY` env var → Keychain → error.
- Keychain integration is via the `keyring` library (`src/aiir/keychain.py`).
- On headless/CI environments where Keychain is unavailable, fall back to env var or `.env`.

### macOS IR Tool Recognition
When analyzing IR conversations on macOS, recognize these platform-specific tools:
- **Unified Logging**: `log show`, `log stream`, `log collect` (Apple ULS)
- **Diagnostics**: `sysdiagnose`, `system_profiler`, `ioreg`
- **Process/File**: `fs_usage`, `dtrace`, `dtruss`, `lsof`, `opensnoop`
- **Launch Services**: `launchctl`, `/Library/LaunchAgents/`, `/Library/LaunchDaemons/`
- **Security**: `spctl` (Gatekeeper), `codesign`, `security` (Keychain CLI), `csrutil` (SIP)
- **File System**: `xattr` (extended attributes / quarantine), `diskutil`, `tmutil` (Time Machine)
- **Network**: `nettop`, `networksetup`, `scutil`, `pfctl`
- **Directory Services**: `dscl`, `id`, `groups`

### file:// URL Defanging
macOS logs (quarantine events, Gatekeeper blocks, crash reports) often contain
`file://` URLs referencing local paths. These are defanged to `fxxle://` by
`parser/defang.py`. Only the scheme is replaced; path dots are left intact
as they represent filesystem paths, not network hostnames.

### .gitignore macOS Entries
`.gitignore` includes macOS-specific patterns: `.DS_Store`, `._*` (resource forks),
`.AppleDouble`, `.LSOverride`, `.Spotlight-V100`, `.Trashes`.
