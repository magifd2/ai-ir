# ai-ir システムアーキテクチャ

## 概要

`ai-ir` は、インシデントレスポンス用 Slack 会話履歴を AI で解析するコマンドラインツールセットです。
scat/stail によるエクスポートを処理し、セキュリティ前処理を施した上で、
OpenAI 互換の LLM API を使って構造化された分析結果を生成します。

## コンポーネント図

```
入力（scat/stail JSON エクスポート）
         │
         ▼
┌─────────────────────┐
│   aiir ingest       │  ← parser/loader.py
│                     │    parser/defang.py
│  - 読み込み・検証   │    parser/sanitizer.py
│  - IoC デファング   │
│  - インジェクション │
│    検出             │
└─────────┬───────────┘
          │ ProcessedExport（JSON）
          ▼
┌─────────────────────────────────────────────────────┐
│                    LLM クライアント                  │
│                  llm/client.py                      │
│                                                     │
│  OpenAI 互換 API（エンドポイント設定可）             │
└─────────────────────────────────────────────────────┘
          │
          ├──────────────────────────────────────────┐
          ▼                                          ▼
┌──────────────────┐  ┌──────────────┐  ┌────────────────────┐
│ analyze/         │  │ analyze/     │  │ analyze/           │
│ summarizer.py    │  │ activity.py  │  │ roles.py           │
│                  │  │              │  │                    │
│ IncidentSummary  │  │ ActivityAna- │  │ RoleAnalysis       │
└──────────────────┘  │ lysis        │  └────────────────────┘
                      └──────────────┘
          │
          ▼
┌──────────────────┐
│ knowledge/       │
│ extractor.py     │  → list[Tactic]
│ formatter.py     │  → YAML ファイル
└──────────────────┘
          │
          ▼
┌──────────────────┐
│ report/          │
│ generator.py     │  → Markdown / JSON レポート
└──────────────────┘
          │
          ▼
┌──────────────────┐
│ server/          │  ← app.py / routes.py
│ (aiir serve)     │    loader.py / templates/
│                  │
│ 読み取り専用     │    127.0.0.1:8765
│ Web UI           │
└──────────────────┘
```

## モジュール責務

### `aiir.config`
`pydantic-settings` を使って環境変数から設定を読み込みます。
`python-dotenv` を通じて `.env` ファイルにも対応しています。
LLM 関連の設定はすべて `AIIR_LLM_` プレフィックスを使用します。

### `aiir.models`
すべての Pydantic データモデルを定義します：
- **入力モデル**: `SlackMessage`、`SlackExport`
- **前処理済みモデル**: `IoC`、`ProcessedMessage`、`ProcessedExport`
- **分析モデル**: `IncidentSummary`、`ActivityAnalysis`、`RoleAnalysis`
- **ナレッジモデル**: `Tactic`、`TacticSource`

### `aiir.parser`
3 段階のパイプライン：
1. **loader**: JSON を `SlackExport` スキーマに対してデシリアライズ・検証
2. **defang**: IoC（IP アドレス、URL、ハッシュ、メールアドレス）を抽出してデファング
3. **sanitizer**: プロンプトインジェクションパターンを検出し、安全タグでテキストをラップ

### `aiir.llm`
OpenAI Python SDK の薄いラッパーです。以下をサポートします：
- 通常のチャット補完（`complete`）
- JSON モード補完（`complete_json`）
- OpenAI 互換エンドポイントへの接続（`base_url` 設定可能）

### `aiir.analyze`
3 つのアナライザー。それぞれ専用のシステムプロンプトと構造化された JSON 出力を持ちます：
- **summarizer**: タイムライン、深刻度、根本原因、解決策
- **activity**: ユーザーごとのアクション（目的・手法・調査結果）
- **roles**: 信頼度と根拠付きの IR ロール推定

### `aiir.knowledge`
- **extractor**: 再利用可能な調査戦術を LLM に抽出させる
- **formatter**: 戦術を生成 ID 付きの YAML にシリアライズする

### `aiir.report`
すべての分析結果を集約して、統合された Markdown または JSON レポートを生成します。

### `aiir.server`
分析出力を閲覧するための読み取り専用ローカル Web UI を提供します：
- **app**: FastAPI アプリケーションファクトリ（`create_app(data_dir)`）— Jinja2 テンプレートとルートを設定
- **routes**: 全ページと JSON API の HTTP ハンドラ：
  - `GET /` — ダッシュボード（レポート件数・深刻度内訳・戦術カテゴリ統計）
  - `GET /report?path=...` — タブ式レポートビュー（サマリ / 活動 / 役割 / 戦術）
  - `GET /knowledge` — フィルタ可能なナレッジライブラリ（カテゴリ・タグ絞り込み）
  - `GET /tactic?path=...` — 戦術詳細ビュー
  - `GET /api/reports` — 全レポートの JSON 一覧
  - `GET /api/knowledge` — 全戦術の JSON 一覧
- **loader**: 安全なファイル探索 — データディレクトリを再帰的にスキャンし、レポート JSON（`"summary"` + `"tactics"` キーで識別）と戦術 YAML（`id` が `"tac-"` 始まりで識別）を収集。パストラバーサルはパスを解決してデータディレクトリ内に収まることを確認することで防止。
- **templates**: Tailwind CSS CDN スタイルの Jinja2 HTML テンプレート（日本語 UI）

### `aiir.cli`
Click ベースの CLI で 7 つのサブコマンドを提供します。各分析コマンドは、
入力がローエクスポートか前処理済みファイルかを自動検出し（`security_warnings`
フィールドの有無で判定）、必要に応じてインジェスト処理を実行します。

## データフロー

```
生 JSON → SlackExport → ProcessedExport → LLM API → 分析モデル → レポート/YAML
```

## セキュリティアーキテクチャ

ユーザー由来のデータはすべて、LLM に渡される前に 2 段階のセキュリティパイプラインを通ります：

1. **デファング**（`parser/defang.py`）: IoC をデファング済みの表現に置換することで、
   悪意のある URL や IP アドレスが誤って有効化されないようにします。
2. **サニタイズ**（`parser/sanitizer.py`）: テキストを 14 種類以上のプロンプトインジェクション
   パターンに対してスキャンし、nonce 付き XML ブロック（`<user_message_{nonce}>`）でラップして、
   その内容がデータであり命令ではないことを LLM に伝えます。暗号学的にランダムな nonce を
   `aiir ingest` 実行ごとに 1 つ生成し、そのセッション内の全メッセージと LLM システムプロンプトで共有します。

LLM クライアントはネットワークリクエストを行う唯一のコンポーネントであり、
通信先は設定されたエンドポイントのみです。
