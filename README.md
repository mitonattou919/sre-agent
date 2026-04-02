# SRE Agent

Azure環境向けSREエージェント。CLIから自然言語でAzureアラートやコストを確認できます。

## アーキテクチャ

```
CLI (Click)  →  Orchestrator (FastAPI + Google ADK)  →  MCP Server (FastMCP)  →  Azure APIs
```

| コンポーネント | 技術スタック |
|---|---|
| CLI | Click + httpx + rich |
| Orchestrator | FastAPI + Google ADK + Gemini 2.5 Flash |
| MCP Server | FastMCP (Streamable HTTP) |
| 認証 | Entra ID JWT (API) / Device Code Flow (CLI) |

## 前提条件

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` または `brew install uv`)

## セットアップ

```bash
git clone https://github.com/mitonattou919/sre-agent.git
cd sre-agent

# 依存関係のインストール
uv sync --all-extras
```

## 環境変数

`.env.example` をコピーして編集します。

```bash
cp .env.example .env
```

### ローカル開発（最小設定）

```env
# MCP Server
USE_MOCK=true

# Orchestrator
GEMINI_API_KEY=AIza...
MCP_SERVER_URL=http://localhost:7071/mcp
SKIP_AUTH=true

# CLI
ORCHESTRATOR_URL=http://localhost:8000
SKIP_AUTH=true
```

> `USE_MOCK=true` のときはAzure認証不要です。`GEMINI_API_KEY` のみ実際の値が必要です。

## ローカル起動

### 1. MCP Server を起動

```bash
USE_MOCK=true uv run python -m mcp_server.function_app
# → http://localhost:7071/mcp で待機
```

### 2. Orchestrator を起動（別ターミナル）

```bash
SKIP_AUTH=true \
GEMINI_API_KEY=your_key \
MCP_SERVER_URL=http://localhost:7071/mcp \
uv run uvicorn orchestrator.main:app --reload
# → http://localhost:8000 で待機
```

### 3. CLI で動作確認

```bash
# インタラクティブモード
SKIP_AUTH=true ORCHESTRATOR_URL=http://localhost:8000 \
  uv run sre-agent

# ワンショット: アラート一覧
SKIP_AUTH=true ORCHESTRATOR_URL=http://localhost:8000 \
  uv run sre-agent alerts

# ワンショット: コスト確認
SKIP_AUTH=true ORCHESTRATOR_URL=http://localhost:8000 \
  uv run sre-agent cost --period 7d
```

### インタラクティブモードの使い方

```
$ uv run sre-agent
Session: abc-123
SRE Agent ready. Type /help for commands.

> アクティブなアラートを教えて
🔧 get_alerts
## アクティブなアラート (2件)
...

> /help
Available commands:
  /exit, /quit   Exit interactive mode
  /session       Show current session ID
  /help          Show this help

> /exit
Goodbye.
```

## CLIコマンド一覧

```bash
uv run sre-agent                              # インタラクティブモード
uv run sre-agent login                        # Entra ID認証（Device Code Flow）
uv run sre-agent chat                         # インタラクティブモード（エイリアス）
uv run sre-agent alerts                       # アラート一覧
uv run sre-agent alerts --resource-group rg-prod --severity 0
uv run sre-agent cost                         # コスト確認（デフォルト: 7d）
uv run sre-agent cost --period 30d
```

## テスト実行

```bash
uv run pytest tests/ -v
```

## ディレクトリ構成

```
sre-agent/
├── mcp_server/
│   ├── function_app.py        # FastMCP エントリーポイント（ローカル + Azure Functions）
│   ├── tools/
│   │   ├── alerts.py          # get_alerts 実装
│   │   └── cost.py            # get_cost_summary 実装
│   └── mock/
│       ├── alerts.json        # モックアラートデータ
│       └── cost.json          # モックコストデータ
├── orchestrator/
│   ├── main.py                # FastAPI エンドポイント
│   ├── agent.py               # LlmAgent 定義
│   ├── runner.py              # ADK Runner + セッション管理
│   ├── auth.py                # Entra ID JWT 検証
│   ├── mcp_client.py          # MCPToolset 接続設定
│   └── config.py              # pydantic-settings
├── cli/
│   ├── main.py                # Click エントリーポイント
│   ├── auth.py                # Device Code Flow / トークンキャッシュ
│   ├── client.py              # httpx クライアント
│   └── config.py              # pydantic-settings
├── tests/
│   ├── test_mcp_tools.py
│   ├── test_orchestrator.py
│   └── test_cli.py
├── pyproject.toml
├── .env.example
└── docs/
```

## 本番環境向け設定

本番では `SKIP_AUTH=false` にして Entra ID の設定が必要です。

```env
# Orchestrator
SKIP_AUTH=false
ENTRA_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ENTRA_APP_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# MCP Server（Azure Functions）
USE_MOCK=false
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MCP_FUNCTION_KEY=your_function_key
```

詳細は [`docs/requirements.md`](docs/requirements.md) および [`docs/technical-spec.md`](docs/technical-spec.md) を参照してください。
