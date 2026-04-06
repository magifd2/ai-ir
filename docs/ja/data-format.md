# データフォーマット仕様

## 入力フォーマット：scat/stail/scli JSON エクスポート

[scat](https://github.com/nlink-jp/scat)、[stail](https://github.com/nlink-jp/stail)、
および [scli](https://github.com/nlink-jp/scli) は共通の JSON スキーマでエクスポートを生成します
（正式な仕様は各プロジェクトの `docs/EXPORT_FORMAT.md` を参照）。

### スキーマ

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

### フィールド説明

| フィールド | 型 | 説明 |
|---|---|---|
| `export_timestamp` | ISO 8601 日時 | エクスポートが生成された日時 |
| `channel_name` | string | Slack チャンネル名（例：`#incident-response`） |
| `messages` | array | メッセージオブジェクトの一覧 |

#### メッセージフィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `user_id` | string | Slack ユーザー ID（例：`U12345ABC`） |
| `user_name` | string | 表示名 |
| `post_type` | `"user"` \| `"bot"` | メッセージの発信元種別 |
| `timestamp` | ISO 8601 日時 | メッセージのタイムスタンプ |
| `timestamp_unix` | string | Unix タイムスタンプ（10 進数文字列） |
| `text` | string | メッセージ本文 |
| `files` | array | 添付ファイルオブジェクト（空の場合あり） |
| `attachments` | array | レガシーリッチ添付（空の場合は省略） |
| `blocks` | array | Block Kit JSON ペイロード（空の場合は省略） |
| `thread_timestamp_unix` | string | 親スレッドのタイムスタンプ、またはスレッド外の場合は空文字列 |
| `is_reply` | boolean | スレッド返信かどうか |

`text` が空で `attachments` または `blocks` にコンテンツがある場合、ai-ir は自動的にテキストを抽出し、
下流の分析（IoC 無害化、LLM プロンプト）でメッセージ内容が失われないようにします。

## 前処理済みフォーマット

`aiir ingest` の出力。入力フォーマットにセキュリティメタデータを追加した形式です。

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

### 追加フィールド

#### トップレベル
| フィールド | 型 | 説明 |
|---|---|---|
| `security_warnings` | string[] | 全メッセージから集約した警告の一覧 |
| `sanitization_nonce` | string | `<user_message_{nonce}>` ラッピングタグに埋め込まれるランダム16進数文字列。タグ名の推測によるプロンプトインジェクションを防ぐ |

#### メッセージごと
| フィールド | 型 | 説明 |
|---|---|---|
| `iocs` | IoC[] | 抽出・デファング済みの侵害指標 |
| `has_injection_risk` | boolean | インジェクションパターンが検出されたかどうか |
| `injection_warnings` | string[] | 検出されたインジェクションパターンの説明 |

### IoC オブジェクト

```json
{
  "original": "192.168.1.100",
  "defanged": "192[.]168[.]1[.]100",
  "type": "ip"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `original` | string | 元の IoC の値 |
| `defanged` | string | デファング済みの表現 |
| `type` | string | IoC の種別：`ip`、`url`、`domain`、`email`、`hash` |

## 分析出力フォーマット

### インシデントサマリ（JSON）

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

### 活動分析（JSON）

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

### ロール分析（JSON）

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

### タクティクス（JSON）

タクティクスは `aiir report` が生成するレポート JSON の `"tactics"` 配列に含まれ、個別の YAML ファイルとしても保存されます（[knowledge-format.md](knowledge-format.md) 参照）。

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

### IncidentReview（JSON）

`aiir review` の出力。元レポートと同じディレクトリに `<stem>.review.json` として保存されます。

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
