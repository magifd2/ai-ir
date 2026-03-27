# Data Format Specifications

## Input Format: scat/stail JSON Export

Both [scat](https://github.com/nlink-jp/scat) and [stail](https://github.com/nlink-jp/stail)
produce exports in the same JSON schema.

### Schema

```json
{
  "export_timestamp": "2026-03-19T10:00:00Z",
  "channel_name": "#incident-response",
  "messages": [
    {
      "user_id": "U12345ABC",
      "user_name": "alice",
      "post_type": "user",
      "timestamp": "2026-03-19T09:55:00Z",
      "timestamp_unix": "1742378100.000000",
      "text": "Server at 192.168.1.100 is down.",
      "files": [],
      "thread_timestamp_unix": "",
      "is_reply": false
    }
  ]
}
```

### Field Descriptions

| Field | Type | Description |
|---|---|---|
| `export_timestamp` | ISO 8601 datetime | When the export was generated |
| `channel_name` | string | Slack channel name (e.g. `#incident-response`) |
| `messages` | array | List of message objects |

#### Message Fields

| Field | Type | Description |
|---|---|---|
| `user_id` | string | Slack user ID (e.g. `U12345ABC`) |
| `user_name` | string | Display name |
| `post_type` | `"user"` \| `"bot"` | Message source type |
| `timestamp` | ISO 8601 datetime | Message timestamp |
| `timestamp_unix` | string | Unix timestamp as decimal string |
| `text` | string | Message text content |
| `files` | array | Attached file objects (may be empty) |
| `thread_timestamp_unix` | string | Parent thread ts, or empty string |
| `is_reply` | boolean | Whether this is a thread reply |

## Preprocessed Format

Output of `aiir ingest`. Extends the input format with security metadata.

```json
{
  "export_timestamp": "2026-03-19T10:00:00Z",
  "channel_name": "#incident-response",
  "messages": [
    {
      "user_id": "U12345ABC",
      "user_name": "alice",
      "post_type": "user",
      "timestamp": "2026-03-19T09:55:00Z",
      "timestamp_unix": "1742378100.000000",
      "text": "<user_message_a3f9c1b2d4e5f678>\nServer at 192[.]168[.]1[.]100 is down.\n</user_message_a3f9c1b2d4e5f678>",
      "files": [],
      "thread_timestamp_unix": "",
      "is_reply": false,
      "iocs": [
        {
          "original": "192.168.1.100",
          "defanged": "192[.]168[.]1[.]100",
          "type": "ip"
        }
      ],
      "has_injection_risk": false,
      "injection_warnings": []
    }
  ],
  "security_warnings": [],
  "sanitization_nonce": "a3f9c1b2d4e5f678"
}
```

### Added Fields

#### Top-level
| Field | Type | Description |
|---|---|---|
| `security_warnings` | string[] | Aggregate warnings from all messages |
| `sanitization_nonce` | string | Random hex string embedded in `<user_message_{nonce}>` wrapping tags to prevent prompt injection via tag-name guessing |

#### Per-message
| Field | Type | Description |
|---|---|---|
| `iocs` | IoC[] | Extracted and defanged indicators of compromise |
| `has_injection_risk` | boolean | Whether injection patterns were detected |
| `injection_warnings` | string[] | Descriptions of detected injection patterns |

### IoC Object

```json
{
  "original": "192.168.1.100",
  "defanged": "192[.]168[.]1[.]100",
  "type": "ip"
}
```

| Field | Type | Description |
|---|---|---|
| `original` | string | Original IoC value |
| `defanged` | string | Defanged representation |
| `type` | string | IoC type: `ip`, `url`, `domain`, `email`, `hash` |

## Analysis Output Formats

### Incident Summary (JSON)

```json
{
  "title": "Database cluster outage in production",
  "severity": "critical",
  "affected_systems": ["postgres-prod-01", "api-gateway"],
  "timeline": [
    {
      "timestamp": "2026-03-19T09:55:00Z",
      "actor": "alice",
      "event": "Reported database unreachable"
    }
  ],
  "root_cause": "OOM killer terminated PostgreSQL process",
  "resolution": "Restarted PostgreSQL, increased memory limits",
  "summary": "..."
}
```

### Activity Analysis (JSON)

```json
{
  "incident_id": "#incident-response",
  "channel": "#incident-response",
  "participants": [
    {
      "user_name": "alice",
      "role_hint": "Database SME",
      "actions": [
        {
          "timestamp": "2026-03-19T09:55:00Z",
          "purpose": "Identify failing component",
          "method": "kubectl get pods -n production",
          "findings": "3 database pods in CrashLoopBackOff"
        }
      ]
    }
  ]
}
```

### Role Analysis (JSON)

```json
{
  "incident_id": "#incident-response",
  "channel": "#incident-response",
  "participants": [
    {
      "user_name": "alice",
      "inferred_role": "Lead Responder",
      "confidence": "high",
      "evidence": ["Coordinated investigation", "Assigned tasks to others"]
    }
  ],
  "relationships": [
    {
      "from_user": "bob",
      "to_user": "alice",
      "relationship_type": "reports_to",
      "description": "Bob provided status updates to Alice"
    }
  ]
}
```

### Tactic (JSON)

Tactics are embedded in the full report JSON under `"tactics"` and also saved as individual YAML files (see [knowledge-format.md](knowledge-format.md)).

```json
{
  "id": "tac-20260319-001",
  "title": "Check Pod Logs for OOM Events",
  "purpose": "Identify whether a Kubernetes pod was killed by the OOM killer",
  "category": "container-analysis",
  "tools": ["kubectl", "grep"],
  "procedure": "1. kubectl get pods -n <namespace>\n2. kubectl describe pod <name>",
  "observations": "Exit code 137 indicates OOM kill",
  "tags": ["kubernetes", "oom", "memory"],
  "confidence": "confirmed",
  "evidence": "Alice shared kubectl output showing OOMKilled status in the channel",
  "source": {
    "channel": "#incident-response",
    "participants": ["alice", "bob"]
  },
  "created_at": "2026-03-19"
}
```

### IncidentReview (JSON)

Output of `aiir review`. Saved as `<stem>.review.json` alongside the source report.

```json
{
  "incident_id": "abc123def456",
  "channel": "#incident-response",
  "overall_score": "good",
  "phases": [
    {
      "phase": "detection",
      "estimated_duration": "~5 minutes",
      "quality": "good",
      "notes": "Alert fired quickly after the event."
    },
    {
      "phase": "resolution",
      "estimated_duration": "~30 minutes",
      "quality": "adequate",
      "notes": "Pod restart resolved the symptom; root cause analysis deferred."
    }
  ],
  "communication": {
    "overall": "Team communicated clearly throughout.",
    "delays_observed": [],
    "silos_observed": []
  },
  "role_clarity": {
    "ic_identified": true,
    "ic_name": "alice",
    "gaps": [],
    "overlaps": []
  },
  "tool_appropriateness": "Appropriate tools used; kubectl and log inspection were well-targeted.",
  "strengths": ["Fast detection", "Clear communication"],
  "improvements": ["Add runbook link in channel topic before next incident"],
  "checklist": [
    {"item": "Verify alert thresholds quarterly", "priority": "medium"}
  ]
}
```
