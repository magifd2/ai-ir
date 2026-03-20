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
7. [テスト戦略](#7-テスト戦略)
8. [リリース手順](#8-リリース手順)
9. [トラブルシューティング](#9-トラブルシューティング)

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

**Step 3** — `CLAUDE.md` の Knowledge Format セクションの表を更新する

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

### Web UI に新しいページを追加する

1. `src/aiir/server/routes.py` にルートハンドラを追加する
2. `src/aiir/server/templates/` に Jinja2 テンプレートを作成する
3. 必要に応じて `src/aiir/server/app.py` でルートを登録する
4. `tests/test_server/test_routes.py` にテストを書く

### Web UI のトラブルシューティング

| 症状 | 想定原因 | 対処 |
|---|---|---|
| レポートが表示されない | JSON 形式が期待と異なる | `aiir report` を先に実行、`summary`+`tactics` キーを確認 |
| 戦術が表示されない | YAML の id フィールドに `tac-` プレフィックスがない | フォーマッタ出力を確認、`aiir knowledge` を再実行 |
| ポートが使用中 | ポート 8765 が別プロセスに占有されている | `--port <他のポート>` を使用 |

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

---

## 8. リリース手順

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

## 9. トラブルシューティング

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
