# EDITH 2.0 (Even Dead, I'm The Hero)

A lightweight, responsive, daily task-driven and companion AI assistant built from first principles to master core AI Engineering patterns.

---

## Step 1: The Core Loop (Telegram + Agent Loop + Google Drive + Approval Gate)

Step 1 proves the end-to-end agentic core loop:
1. You message EDITH via Telegram from your phone (e.g., *"Find my OS lecture notes"*).
2. The ReAct agent loop asks Claude to choose the right tool (`search_drive`).
3. Search results are displayed in Telegram.
4. When EDITH is asked to send a file, the **Approval Gate** halts execution and prompts you with interactive **Yes / No** buttons.
5. Only upon tapping **Yes**, the file is fetched from Drive and delivered to your phone.
6. Every single model call, tool execution, and approval event is recorded in a structured JSON audit log.

---

## Architecture

```
Telegram App (Phone)
       ↕ (Long Polling)
Telegram Bot (Single-User Allowlist)
       ↕
Agent Loop (ReAct, Max 6 Iterations) ──↔── Anthropic Claude API
       │
       ├── Read Tools (Runs freely): `search_drive`, `fetch_file`
       │
       └── Send Tools (Approval Gate): `send_file`
             └── Telegram Inline Keyboard (Yes / No Buttons)
```

---

## AI Engineering Concepts Implemented

- **Schema-Validated Tool Calling**: Anthropic tools generated dynamically from `Pydantic v2` models.
- **Error Recovery**: Validation failures and runtime exceptions are fed back into the agent context, allowing self-correction without crashing.
- **Human-in-the-Loop (HITL) Safety**: Risk tiering (`read` vs `send`) with execution halting for sensitive actions.
- **Security & Least Privilege**:
  - Single-user allowlist (`TELEGRAM_USER_ID`) ignoring all unauthorized traffic.
  - Read-only Drive OAuth scope (`https://www.googleapis.com/auth/drive.readonly`).
  - No outbound channels except delivery back to the verified chat.
- **Async Non-Blocking I/O**: Telegram polling runs asynchronously while blocking Google API calls are delegated to worker threads.
- **Sliding-Window Conversation State**: Sliding history buffer retaining context for follow-up questions.
- **Structured JSON Audit Logs**: Line-delimited JSON records (`.jsonl`) tracking token counts, latency, and tool inputs/outputs.
- **Automated Evals (Pytest)**: Comprehensive test suite covering intent classification, bad argument correction, max iteration caps, and approval branching.

---

## Project Structure

```
Edith-2.0/
├── edith/
│   ├── __init__.py
│   ├── config.py             # Pydantic configuration loader
│   ├── logging.py            # Structured JSON audit logging
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py           # ReAct loop with Anthropic API
│   │   └── state.py          # State tracking & sliding memory
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py           # Tool base class & registry
│   │   └── drive.py          # Google Drive search & fetch tools
│   └── telegram/
│       ├── __init__.py
│       ├── bot.py            # Telegram Application builder
│       └── handlers.py       # Message & approval callback handlers
├── tests/
│   ├── conftest.py           # Mock Anthropic client & test fixtures
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_loop.py          # Evals for routing, recovery & caps
│   ├── test_telegram_security.py # Allowlist enforcement tests
│   └── test_tools.py         # Schema generation & validation tests
├── .env.example
├── .gitignore
├── pytest.ini
├── main.py                   # Bot entrypoint
└── README.md
```

---

## Setup & Quickstart

### 1. Requirements
- Python 3.11+
- Virtual environment created via `uv` or `venv`

### 2. Run Test Suite (Offline / CI)
No external credentials needed to run the test suite:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

### 3. Configure Live Credentials
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Fill in your credentials:
- `TELEGRAM_BOT_TOKEN`: From [@BotFather](https://t.me/BotFather)
- `TELEGRAM_USER_ID`: Your numerical ID from [@userinfobot](https://t.me/userinfobot)
- `ANTHROPIC_API_KEY`: From the Anthropic Console
- `credentials.json`: Download OAuth 2.0 Client credentials (Desktop Application) from the [Google Cloud Console](https://console.cloud.google.com/) and save in the repository root.

### 4. Run EDITH 2.0
```powershell
.\.venv\Scripts\python.exe main.py
```
*(On first run, a browser tab will open to authorize read-only access to Google Drive, which saves `token.json` locally).*
