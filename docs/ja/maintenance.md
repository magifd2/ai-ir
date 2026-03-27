# ai-ir メンテナンスガイド

このドキュメントは ai-ir ツールセットを継続的に維持・改善するための手順書です。

---

## 目次

1. [日常的なメンテナンス](#1-日常的なメンテナンス)
2. [依存関係の管理](#2-依存関係の管理)
3. [プロンプトのメンテナンス](#3-プロンプトのメンテナンス)
4. [知識カテゴリの追加・変更](#4-知識カテゴリの追加変更)
5. [セキュリティメンテナンス](#5-セキュリティメンテナンス)
6. [新機能の追加手順](#6-新機能の追加手順)
6.4. [ナレッジ抽出（aiir report 経由）](#64-ナレッジ抽出aiir-report-経由)
6.5. [Web UI（aiir serve）](#65-web-uiaiir-serve)
6.6. [翻訳（aiir translate）](#66-翻訳aiir-translate)
6.7. [プロセス評価（aiir review）](#67-プロセス評価aiir-review)
7. [テスト戦略](#7-テスト戦略)
8. [LLM 互換性](#8-llm-互換性)
9. [リリース手順](#9-リリース手順)
10. [トラブルシューティング](#10-トラブルシューティング)

---

## 1. 日常的なメンテナンス

### テストの実行

```bash
# 全テスト（推奨：変更前後に必ず実行）
uv run pytest tests/ -v

# カバレッジ付き
uv run pytest tests/ --cov=src/aiir --cov-report=term-missing

# 特定モジュールのみ
uv run pytest tests/test_parser/ -v
uv run pytest tests/test_knowledge/ -v
```

### 設定の確認

```bash
# 現在の設定を確認（APIキーはマスク表示）
aiir config show
```

---

## 2. 依存関係の管理

### 定期更新（月1回推奨）

```bash
# uv.lock を最新化
uv lock --upgrade

# 更新された依存関係をインストール
uv sync

# テストで回帰がないことを確認
uv run pytest tests/ -v
```

### セキュリティ脆弱性チェック

```bash
# pip-audit で既知の脆弱性をスキャン（要インストール）
uv add --dev pip-audit
uv run pip-audit
```

脆弱性が見つかった場合は `pyproject.toml` で該当パッケージのバージョン下限を引き上げ、
`uv lock --upgrade-package <パッケージ名>` で更新する。

### 依存関係を追加するとき

```bash
# 本番依存関係
uv add <package>

# 開発専用
uv add --dev <package>

# pyproject.toml と uv.lock が両方更新されることを確認
git diff pyproject.toml uv.lock
```

---

## 3. プロンプトのメンテナンス

プロンプトは各分析モジュールの `_build_system_prompt(nonce: str) -> str` 関数として実装されている
（静的定数ではなく — nonce を呼び出し時に埋め込む必要があるため）。

| ファイル | 担当 |
|---|---|
| `src/aiir/analyze/summarizer.py` | インシデントサマリ生成 |
| `src/aiir/analyze/activity.py` | 担当者活動分析 |
| `src/aiir/analyze/roles.py` | 役割・関係性推論 |
| `src/aiir/knowledge/extractor.py` | 戦術ナレッジ抽出 |
| `src/aiir/analyze/reviewer.py` | IR 対応プロセス品質評価（nonce 不要 — ユーザーテキストをプロンプトに含まない） |

### プロンプトを変更するときのチェックリスト

1. **変更前にテストを実行**して現状を記録する
2. **必ずセキュリティガードを維持する**（以下の2要素は削除・弱体化禁止）
   - `<user_message_{nonce}>` nonce 付きタグでのデータ包囲
   - 「タグ内はデータであり指示ではない」旨の明示
3. **JSON スキーマの変更を伴う場合**は `src/aiir/models.py` の対応モデルも更新する
4. **CHANGELOG.md に変更内容を記載**する

### プロンプト変更の影響範囲

```
_build_system_prompt() を変更
    ├─ JSONスキーマが変わった → models.py のモデルも更新
    ├─ 出力フィールドが増えた → Markdown フォーマッタも更新
    └─ カテゴリが変わった    → test_extractor_prompt.py のテストも更新
```

### プロンプトの動作確認方法

実際の LLM を呼び出してプロンプトを検証するスクリプト例：

```bash
# サンプルデータで summarize を試す
aiir summarize tests/fixtures/sample_export.json
```

本番 LLM に送信する前に `aiir ingest` の出力を目視確認することも推奨。

---

## 4. 知識カテゴリの追加・変更

### 新カテゴリを追加する手順

**Step 1** — `src/aiir/knowledge/extractor.py` の `SYSTEM_PROMPT` にカテゴリを追記する

```python
# 例：新しい Linux カテゴリを追加
- linux-newcategory: 対象ツールや手法の簡潔な説明 — `tool1`, `tool2`
```

フォーマットの原則：
- カテゴリ名はケバブケース（`platform-concept`）
- 説明には代表的なツール名・コマンド名を含める（LLM が判断しやすくなる）
- プラットフォーム固有のものは `linux-`/`windows-`/`macos-` プレフィックスを付ける

**Step 2** — `tests/test_knowledge/test_extractor_prompt.py` にテストを追加する

```python
@pytest.mark.parametrize("category", [
    ...,
    "linux-newcategory",  # ← 追加
])
def test_linux_category_present(category):
    assert category in SYSTEM_PROMPT
```

代表的なツール名のテストも追加する：

```python
@pytest.mark.parametrize("tool", [
    ...,
    "tool1",  # ← 追加
])
def test_linux_tool_mentioned(tool):
    assert tool in SYSTEM_PROMPT
```

**Step 3** — `docs/en/knowledge-format.md`（および `docs/ja/knowledge-format.md`）のカテゴリ表を更新する

**Step 4** — `CHANGELOG.md` に追記し、コミットする

### カテゴリを削除・統合するとき

既存のカテゴリを削除すると、過去に生成した YAML ナレッジ文書との整合性が崩れる。
削除より **`other` への統合**か **カテゴリ説明の拡張** を優先すること。

削除が不可避な場合は：
1. 移行先カテゴリを決める
2. 既存の YAML ファイルを一括置換する（`sed -i` または Python スクリプト）
3. テストを更新する

---

## 5. セキュリティメンテナンス

### IoC Defang パターンの拡張

新しい IoC タイプ（例：IPv6、Bitcoin アドレス）が必要になった場合は
`src/aiir/parser/defang.py` を編集する。

追加時の必須事項：
- 正規表現のテストを `tests/test_parser/test_defang.py` に追加する
- false positive（誤検知）と false negative（見逃し）の両方を検証する
- 既存の IoC 処理と **重複しない**こと（`_overlaps()` 関数が保護）

```python
# 新パターン追加の例（defang.py）
_NEW_PATTERN = re.compile(r"...", re.IGNORECASE)

# defang_text() 内の適切な優先順位位置に追加
for m in _NEW_PATTERN.finditer(text):
    if _overlaps(m.start(), m.end(), replacements):
        continue
    ...
```

### プロンプトインジェクション検出パターンの拡張

新しい攻撃パターンを発見した場合は `src/aiir/parser/sanitizer.py` の
`INJECTION_PATTERNS` リストに追記する。

```python
INJECTION_PATTERNS = [
    ...
    r"新しいパターン",  # コメントで発見経緯や参考リンクを記載
]
```

対応するテストを `tests/test_parser/test_sanitizer.py` に追加することを忘れずに。

### APIキーのローテーション

```bash
# Keychain に保存している場合
aiir config delete-key
aiir config set-key   # 新しいキーを入力

# 環境変数で管理している場合
export AIIR_LLM_API_KEY=<新しいキー>
# または .env ファイルを編集
```

インシデント対応でクレデンシャル漏洩が発生した場合は、分析に使用した API キーを
速やかにローテーションすること（`docs/ja/security.md` の推奨事項も参照）。

---

## 6. 新機能の追加手順

### 新しい分析サブコマンドを追加する

以下を順番に実施する：

1. **`src/aiir/models.py`** — 入出力データモデル（Pydantic）を追加する
2. **`src/aiir/analyze/<name>.py`** — 分析ロジックと `SYSTEM_PROMPT` を実装する
3. **`src/aiir/cli.py`** — `@main.command()` でサブコマンドを登録する
4. **`tests/test_analyze/test_<name>.py`** — LLM クライアントをモックしたテストを書く
5. **`CHANGELOG.md`** — 追加内容を記載する
6. **`README.md`** — 使い方の例を追加する

### 新しい入力フォーマットに対応する

現在は scat/stail の JSON export 形式のみサポート。新しいフォーマット（例：Splunk
のエクスポート）に対応する場合：

1. `src/aiir/models.py` に新しいモデル（例：`SplunkExport`）を定義する
2. `src/aiir/parser/loader.py` に対応するローダー関数を追加する
3. `src/aiir/cli.py` の `_load_or_preprocess()` にフォーマット判別ロジックを追加する
4. `tests/fixtures/` にサンプルファイルを追加し、テストを書く

---

## 6.4. レポート生成（`report/generator.py`）

### 設計上の背景：2つの Markdown レンダラー

各分析モジュール（`summarizer`、`activity`、`roles`）はそれぞれ `format_*_markdown()` 関数を提供しており、
H2 トップレベル見出しを持つ**単体完結型** Markdown ドキュメントを生成します。
単独でレンダラーに渡したり別途保存したりする用途に適しています。

一方、`report/generator.py` の `generate_markdown_report()` は、同じセクションが H2 ヘッダー配下の
H3 サブセクションとして現れる**複合レポート**を生成します。レンダリングの詳細も意図的に異なります：

| 観点 | 単体（`format_*_markdown`） | 複合（`generate_markdown_report`） |
|---|---|---|
| アクティビティ見出しレベル | H2（`## @name`） | H3（`### @name`） |
| ロール確度ラベル | `[HIGH]` / `[MED]` / `[LOW]` | `(High confidence)` 等の散文形式 |
| ロール参加者レイアウト | H3 見出し + `**Evidence:**` ブロック | 箇条書き + `_evidence_` サブ箇条書き |
| 関係性テーブル | Description 列を含む4列 | Description 列なしの3列（簡潔さ優先） |

これらは見出し階層と情報密度の要件が異なる、別々の出力文脈のための意図的なバリアントです。
これらの構造的・スタイル的な差異を考慮せずに共通実装に統合しないでください。

### ナレッジ抽出（aiir report 経由）

v0.5.0 で `aiir knowledge` コマンドを廃止しました。以前はレポートとは独立した LLM コールを実行していたため、
抽出されるタクティクスの件数が一致しないという問題がありました。

代わりに `aiir report` のオプションを使用してください：

```bash
# フルレポート + YAML タクティクスを同時保存（推奨）
aiir report preprocessed.json --format json -o report.json --knowledge-dir ./knowledge

# タクティクスのみ抽出（サマリ・活動・ロール分析はスキップ）
aiir report preprocessed.json --knowledge-only --knowledge-dir ./knowledge
```

`--knowledge-dir` はレポートと同じ LLM コールを共有するため、`report.json` の tactics 件数と
YAML ファイルの件数は常に一致します。

### RAG 用 Markdown へのエクスポート

`aiir knowledge export` を使用すると、既存のタクティクス YAML ファイルを RAG ナレッジベース
（例: [lite-rag](https://github.com/nlink-jp/lite-rag)）に取り込むための Markdown ファイルに変換できます。

```bash
# ./knowledge 内の tac-*.yaml をすべて ./knowledge-md/*.md に変換
aiir knowledge export -k ./knowledge -o ./knowledge-md

# 出力先を省略すると <knowledge-dir>-md になる
aiir knowledge export -k ./knowledge
```

**1ファイル1タクティクスにする理由:** 複数タクティクスをまとめたファイルにすると、RAG の検索結果が
近隣タクティクスに引きずられます。1ファイルに絞ることで各ドキュメントが意味的に独立し、精度が上がります。

**各 Markdown ファイルの構造：**

```
# {title}

**ID:** ... | **Category:** ... | **Confidence:** ...
**Tags:** ...
**Source:** ...

## Purpose（目的）
## Tools（ツール）
## Procedure（手順）
## Observations（観察ポイント）
## Evidence（根拠） ← evidence フィールドが空でない場合のみ出力
```

### 設計上の背景：`aiir report` の逐次 LLM 呼び出し

`aiir report` は LLM を 4 回逐次呼び出します（summary → activity → roles → tactics）。
これは主要なターゲット環境に対して意図的な設計です。

**理由:** 主要なターゲットは単一 GPU 上で動作するローカルの [Ollama](https://ollama.com/) です。
Ollama は複数スレッドから同時にリクエストが届いても GPU では逐次処理します。並列 HTTP 呼び出しは単に
GPU キューに積まれるだけでスループットは変わりません。`translate_report`（4 並列）で実測したところ
103.7 s → 78.9 s（1.31×）にとどまり、理論最大値には遠く及びませんでした。GPU がボトルネックだった
ためです。

`translate_report` と `translate_review` は並列化済みです。これらの 4 セクションは独立しており、
共有状態がないため並列化に適しています。

**クラウド API 環境**（OpenAI、Anthropic 等）では並列化で 3〜4× の高速化が期待できます。クラウド利
用が主要なユースケースになり、レポート生成時間が問題になった場合は再検討します。

---

## 6.5. Web UI（`aiir serve`）

`aiir serve` コマンドは、レポートとナレッジ文書を閲覧するための読み取り専用ローカル Web サーバーを起動します。

### 使い方

```bash
# カレントディレクトリをスキャン、ポート 8765 で起動、ブラウザ自動起動
aiir serve

# データディレクトリとポートを指定
aiir serve /path/to/analysis --port 9000

# ブラウザを自動起動しない
aiir serve --no-browser
```

### セキュリティ

サーバーは**必ず `127.0.0.1`（ローカルホスト）にバインド**され、ネットワークからはアクセスできません。
パストラバーサル攻撃はファイルパスを解決してデータディレクトリ内に収まることを確認することで防止されます。

### ファイル探索

サーバーはデータディレクトリを再帰的にスキャンして以下を収集します：
- **レポート JSON** — `"summary"` と `"tactics"` のキーを両方持つファイル
- **戦術 YAML** — `id` フィールドが `"tac-"` で始まるファイル

### 設計上の背景：リクエストごとのディレクトリスキャン（キャッシュなし）

`routes.py` はダッシュボードリクエストのたびに `scan_reports()` と `scan_tactics()` を呼び出します。
キャッシュは意図的に実装していません。

**理由:** `aiir serve` は単一アナリストがローカルで使う読み取り専用ツールです。典型的なワークフローは
別ターミナルで `aiir report` や `aiir review` を実行しながらサーバーを起動し続けることです。キャッシュ
を実装するとキャッシュ期限切れまで古いスキャン結果を表示してしまいます。毎回スキャンすることで、常に
最新のファイルシステム状態をユーザーに見せられます。

**パフォーマンス:** ローカル SSD で数十件の JSON/YAML をスキャンするのは数ミリ秒です。単一ユーザーの
インタラクティブツールとして知覚できる遅延しきい値を大きく下回ります。

**再検討のタイミング:** 特定のデータセット規模でページ読み込みの遅延が報告された場合、正しい解決策は
時間ベースのキャッシュではなくファイルシステム監視（例: `watchfiles`）です。監視なら陳腐化を防ぎつつ
スキャン頻度を減らせます。

### Web UI に新しいページを追加する

1. `src/aiir/server/routes.py` にルートハンドラを追加する
2. `src/aiir/server/templates/` に Jinja2 テンプレートを作成する
3. 必要に応じて `src/aiir/server/app.py` でルートを登録する
4. `tests/test_server/test_routes.py` にテストを書く

### Web UI のトラブルシューティング

| 症状 | 想定原因 | 対処 |
|---|---|---|
| レポートが表示されない | JSON 形式が期待と異なる | `aiir report` を先に実行、`summary`+`tactics` キーを確認 |
| 戦術が表示されない | YAML の id フィールドに `tac-` プレフィックスがない | フォーマッタ出力を確認、`aiir report --knowledge-only -k ./knowledge` を再実行 |
| ポートが使用中 | ポート 8765 が別プロセスに占有されている | `--port <他のポート>` を使用 |

---

## 6.6. 翻訳（aiir translate）

`aiir translate` コマンドは `aiir report --format json` で生成したレポート JSON を受け取り、
ナラティブフィールドを対象言語に翻訳したコピーを保存します。
技術的なコンテンツ（ツール名・コマンド・IOC・ID・タグ）は英語のまま保持されます。

### 使用方法

```bash
# 日本語に翻訳 — デフォルト出力は report.ja.json
aiir translate report.json --lang ja

# 出力先を明示指定
aiir translate report.json --lang zh -o report.zh.json
```

### 翻訳対象フィールドと保持フィールド

| フィールド | 翻訳 |
|---|---|
| `summary.title`, `root_cause`, `resolution`, `summary` | される |
| `summary.timeline[].event` | される |
| `activity.participants[].role_hint` | される |
| `activity.participants[].actions[].purpose`, `findings` | される |
| `roles.participants[].inferred_role`, `evidence` | される |
| `roles.relationships[].description` | される |
| `tactics[].title`, `purpose`, `procedure`, `observations` | される |
| `activity.actions[].method`（コマンド類） | **されない** |
| `tactics[].tools`, `tags`, `category`, `id` | **されない** |
| バッククォートで囲まれたコード | **されない** |
| IOC・ユーザー名・チャンネル名・タイムスタンプ | **されない** |

### 設計上の注意点

- **分析は常に英語で実行**: 全分析プロンプトに `IMPORTANT: Always respond in English regardless of the language of the input conversation.` を追加済み。ローカルの小規模モデルが入力会話の言語（日本語等）に「気を利かせて」切り替えることを防止します。
- **翻訳は独立したステップ**: 英語のソース JSON が正規データとして保持され、翻訳版は補助的な出力です。
- **LLM コール数**: レポート 1 件につき 4 回（summary・activity・roles・tactics 各 1 回）。セクションごとに分けてコンテキストを短く保ち、トークン枯渇リスクを低減します。
- **フォールバック保証**: 翻訳 LLM がフィールドを返さなかった場合、元の英語値がそのまま保持されます。翻訳失敗でレポートデータが欠損することはありません。

### サポート言語（組み込みラベル）

| コード | 言語 |
|---|---|
| `ja` | 日本語 |
| `zh` | 簡体字中国語 |
| `ko` | 韓国語 |
| `de` | ドイツ語 |
| `fr` | フランス語 |
| `es` | スペイン語 |

未登録の言語コードも使用可能です。BCP-47 コードをそのまま LLM の目標言語名として渡します。

### トラブルシューティング

| 症状 | 想定原因 | 対処 |
|---|---|---|
| 一部フィールドが翻訳されない | LLM が技術的な文字列を「コード」と判断 | ツール名・コマンドが英語のまま残るのは正常動作 |
| JSON パースエラー | LLM が不正な JSON を返した | `json-repair` でほぼ自動修正される。解決しない場合は高性能モデルを試す |
| 入力ファイル拒否 | `summary` または `tactics` キーが存在しない | `aiir report --format json` で生成した JSON を指定する |

---

## 6.7. プロセス評価（`aiir review`）

`aiir review` コマンドは、完成したレポート JSON を入力として、インシデントの技術的内容ではなく
対応「プロセス」の品質を LLM で評価します。

### 使用方法

```bash
# プロセス評価 — report.review.json をソースレポートの隣に出力
aiir review report.json

# Markdown 出力（読み共有用）
aiir review report.json --format markdown -o review.md
```

### 評価内容

| 評価軸 | 内容 |
|---|---|
| フェーズ所要時間 | 各 IR フェーズ（検知 / 初動 / 封じ込め / 解決）の推定時間と品質評価 |
| コミュニケーション品質 | 情報共有の遅延・サイロ化の有無 |
| 役割の明確さ | IC の特定、役割の空白・重複 |
| ツール選択の適切さ | 使用したツール・手法の妥当性 |
| 強み | チームが上手くできたこと |
| 改善提案 | 次回に向けた具体的・実行可能な提案 |
| 次回インシデント向けチェックリスト | 優先度付き準備事項（high / medium / low） |

### 出力ファイルの規約

デフォルトでは `aiir review report.json` はソースファイルの隣に `report.review.json` を書き出します。
Web ダッシュボード（`aiir serve`）はこのファイルを自動検出し、レポート詳細ビューに **対応評価** タブを表示します。
翻訳版レポート（例：`report.ja.json`）も同じ `report.review.json` を参照します。

### 設計上のポイント

- **生メッセージの再送なし**: `reviewer.py` は LLM への入力にレポートの構造化済みセクション
  （summary / activity / roles / tactics）のみを使用し、生の Slack メッセージテキストを再送しません。
  トークン消費を抑え、このステップにおけるプロンプトインジェクションリスクをなくします。
- **nonce 不要**: ユーザー由来テキストをプロンプトに含まないため、nonce タグによるラッピングが不要です。
- **英語出力の強制**: 他の分析モジュールと同様に `IMPORTANT: Always respond in English…` 指示を含みます。

### トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| 対応評価タブが表示されない | `report.review.json` が見つからない | `aiir review report.json` を先に実行する |
| 出力が短い・汎用的 | レポートの活動・役割データが少ない | `aiir report` の全パイプラインを先に実行してからレビューする |
| JSON パースエラー | LLM が不正な JSON を返した | リトライするか、より高性能なモデルに切り替える |

---

## 7. テスト戦略

### テストの種類と責務

| テスト種別 | 場所 | 内容 |
|---|---|---|
| ユニットテスト | `tests/test_parser/` | defang・sanitizer の入出力を直接検証 |
| プロンプト内容テスト | `tests/test_knowledge/test_extractor_prompt.py` | `_build_system_prompt()` 出力にカテゴリ・ツール名が存在するか |
| モック統合テスト | `tests/test_llm/` | LLM クライアントの API 呼び出し形式を検証 |
| フォーマッタテスト | `tests/test_knowledge/test_formatter.py` | YAML 出力の構造を検証 |
| Keychain テスト | `tests/test_keychain/` | インメモリモック keyring で動作確認 |
| サーバーテスト | `tests/test_server/` | FastAPI ルートのレスポンスとパストラバーサル防止を検証 |

### LLM を使う機能のテスト方針

LLM（OpenAI API）を実際に呼び出すテストは **書かない**。理由：

- コストが発生する
- 応答が非決定的で CI が不安定になる
- レート制限に引っかかる

代わりに `unittest.mock.patch` で `OpenAI` クラスをモックし、
クライアントが正しいパラメータ（`model`, `messages`, `response_format`）で
API を呼び出すことを検証する。分析ロジックの正しさは
プロンプト内容テストと手動検証で担保する。

### テストを書くときの原則

- **Arrange / Act / Assert** の3段構成を守る
- テスト名は `test_<対象>_<条件>_<期待結果>` 形式を推奨
- `pytest.mark.parametrize` を積極的に使い、境界値・正常値・異常値を網羅する
- 一つのテスト関数で一つのことだけ検証する

### テストスコープの境界

**サードパーティライブラリの内部動作はテスト対象外です。** 自分たちが書くのは「ライブラリとの統合」のテストであり、
ライブラリ自体の動作テストではありません。例：
- `json_repair`: `complete_json()` が様々な LLM レスポンス形式（reasoning タグ、markdown fence 等）に対して
  有効な JSON を返すことを検証します。`repair_json()` そのものを直接テストするのはライブラリの責任です。
- 外部バリデータ（Pydantic）: 自分たちのモデルが期待する入力を受け入れ・拒否することを検証します。
  Pydantic の型強制ロジック自体はテストしません。

**暗黙的なカバレッジが十分な場合、孤立したテストを無理に追加しない。** 上位レベルのテストが現実的な入力で
すでにある関数を実行しているなら、狭い内部動作だけを対象にした分離テストを追加する価値は薄れます。
実装が変わるたびに更新が必要な壊れやすいテストになりかねないためです。`defang.py` の `_overlaps()` ガードが
その例です。既存の defang テストが現実的なマルチ IoC 入力でこの関数を実行しており、人工的なオーバーラップを
構築するテストは現在の正規表現実装に密結合するだけで意味ある新規カバレッジを追加しません。

判断基準は「**このコードにバグがあった場合、既存のテストが検知できるか？**」です。
Yes なら、新規テストの追加は安全性向上よりも保守コスト増加につながります。

---

## 8. LLM 互換性

### レスポンス正規化パイプライン

`llm/client.py` は LLM の出力を呼び出し元に返す前に正規化します：

```
生レスポンス
  │
  ├─ _strip_reasoning_blocks()   <think>, <thinking>, <reasoning>,
  │                               <reflection>, <scratchpad>, <analysis>,
  │                               [THINK]...[/THINK] を除去
  │                               <answer>...</answer> は中身を抽出
  │
  └─ repair_json()               Markdown コードフェンスの除去・JSON 軽微修正
```

このパイプラインは全モデルに対して `complete_json()` 内で自動実行されます。

### 対応する応答フォーマットモード

| モード | 発動条件 | 備考 |
|---|---|---|
| `json_object` | デフォルト（OpenAI・多くの API） | 有効な JSON を保証 |
| `text` フォールバック | 初回呼び出しで `BadRequestError` | LM Studio・多くのローカル LLM で使用 |

### 新しい推論タグへの対応手順

新しいモデルが未対応のタグ形式で推論ブロックを出力する場合：

1. `src/aiir/llm/client.py` の `_REASONING_TAGS` にタグ名を追加する
2. `tests/test_llm/test_client.py` にパラメータ化テストを追加する

角括弧形式（例：Mistral の `[THINK]`）の場合は、新しい正規表現定数を追加して
`_strip_reasoning_blocks()` 内で `.sub()` を呼び出す。

### 対応する入力フォーマット

| フォーマット | 検出方法 | 発生源 |
|---|---|---|
| 単一 JSON オブジェクト | `json.loads()` が成功 | scat エクスポート |
| NDJSON（1行1オブジェクト） | `json.loads()` が "Extra data" エラー | stail エクスポート |

---

## 9. リリース手順

### バージョン番号のポリシー

[Semantic Versioning](https://semver.org/) に従う：

| 変更の種類 | バージョン |
|---|---|
| セキュリティ修正、バグ修正 | PATCH（x.y.**Z**） |
| 新カテゴリ追加、プロンプト改善、新サブコマンド | MINOR（x.**Y**.0） |
| データモデルの破壊的変更、CLI インターフェースの変更 | MAJOR（**X**.0.0） |

### リリース手順

```bash
# 1. テストが全てパスすることを確認
uv run pytest tests/ -v

# 2. src/aiir/__init__.py のバージョンを更新
#    __version__ = "x.y.z"

# 3. pyproject.toml の version を更新
#    version = "x.y.z"

# 4. CHANGELOG.md の [Unreleased] を [x.y.z] - YYYY-MM-DD に変更し、
#    新しい [Unreleased] セクションを先頭に追加

# 5. コミット
git add src/aiir/__init__.py pyproject.toml CHANGELOG.md
git commit -m "chore: release v x.y.z"

# 6. タグ
git tag vx.y.z
```

### CHANGELOG の記述方法

```markdown
## [x.y.z] - YYYY-MM-DD

### Added
- 新機能の説明

### Changed
- 変更の説明（破壊的変更には「**Breaking:**」を先頭に付ける）

### Fixed
- バグ修正の説明

### Security
- セキュリティ修正の説明
```

---

## 10. トラブルシューティング

### `AIIR_LLM_API_KEY is not configured` エラー

```bash
# 設定状況を確認
aiir config show

# 環境変数で設定
export AIIR_LLM_API_KEY=<your-key>

# または Keychain に保存
aiir config set-key
```

### LLM が JSON を返さない / JSON パースエラー

`complete_json()` は `response_format={"type": "json_object"}` を指定しているが、
一部のモデルや自己ホストモデルはこのモードを無視することがある。

対処法：
1. モデルが JSON mode に対応しているか確認する
2. `AIIR_LLM_MODEL` を変更して別のモデルを試す
3. LLM のレスポンスが JSON として有効かどうかを `--debug` ログで確認する

### `ingest` で大量の injection risk 警告が出る

IRの会話には攻撃者のコマンドや疑似命令が含まれることが多く、誤検知が発生しやすい。
`src/aiir/parser/sanitizer.py` の `INJECTION_PATTERNS` を調整して
false positive を減らすことができる。

変更時は既存テストが引き続きパスすることを確認すること。

### uv sync が sandbox 環境で失敗する

```bash
# キャッシュディレクトリを書き込み可能な場所に変更して再実行
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

### テストが突然失敗する（プロンプトテスト）

`test_extractor_prompt.py` はプロンプト文字列にカテゴリ名・ツール名が
含まれることを検証している。プロンプトを編集した後にテストが落ちた場合は：

1. 削除・変更したカテゴリ名やツール名を特定する
2. テストを対応して更新するか、プロンプトの変更を見直す
3. 削除したカテゴリが既存の YAML ナレッジ文書で使われていないか確認する
