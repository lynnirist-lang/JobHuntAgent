# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Job Hunt Agent** (求职助手) is a full-stack automation tool targeting BOSS 直聘 (Chinese job platform). It scrapes jobs, scores them with AI, adapts resumes per JD, generates personalized greeting messages, and applies automatically — all with human-in-the-loop approval before any action is taken.

## Development Commands

### Backend (Python FastAPI)

```bash
# Start backend — MUST use run.py on Windows (sets ProactorEventLoop for Patchright)
python run.py

# Or via uvicorn directly (Linux/macOS only)
uvicorn backend.main:app --reload --port 8080

# Install Python dependencies
pip install -r requirements.txt

# Install Chromium for Patchright (browser automation)
python -m patchright install chromium

# Run tests
pytest backend/tests/ -v
pytest backend/tests/ -v -m "not slow"   # skip tests that need real API keys
```

### Frontend (Next.js 14)

```bash
cd frontend
npm install
npm run dev        # dev server (default :3001)
npm run build
npm run lint
```

### Full Stack

```bash
./start.sh         # starts backend + frontend in parallel
./start.sh backend # backend only
./start.sh frontend # frontend only
```

## Required Configuration

Before first run:

1. Copy `.env` from `.env.example` (or create it). Key variables:
   ```
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_MODEL=deepseek-v4-flash
   DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
   DATABASE_URL=sqlite+aiosqlite:///./data/jobs.db
   BACKEND_PORT=8080
   FRONTEND_PORT=3001
   HF_HUB_OFFLINE=1   # if using pre-downloaded embedding model
   ```

2. Copy `user_profile.example.json` → `user_profile.json` and fill in resume data.

3. First browser launch: manually log into BOSS 直聘; cookies are saved to `data/boss_cookies.json`.

## Architecture

### Data Flow

```
BOSS 直聘 (browser) → ScrapeJobsSkill → ScoreJobsSkill → GenerateGreetingSkill
                                                                    ↓
                                                    User approves via frontend UI
                                                                    ↓
                                                          ApplyJobSkill (with Gaussian delay)
```

### Backend Structure

- **`backend/main.py`** — FastAPI app factory; mounts all routers; lifespan: init DB, start scheduler, warm embedder
- **`backend/run.py`** — Windows entry point; must be used on Windows to set ProactorEventLoop before uvicorn loads
- **`backend/agent/orchestrator.py`** — `HermesOrchestrator`: coordinates the full pipeline in order: scrape → score → greet → enqueue → flush
- **`backend/agent/scheduler.py`** — APScheduler; runs orchestrator on a configurable time window (default 09:20–22:30); always flushes cooldown queue every 5 min
- **`backend/skills/`** — Composable, independently testable units: `ScrapeJobsSkill`, `ScoreJobsSkill`, `GenerateGreetingSkill`, `ApplyJobSkill`, `AdaptResumeSkill`, `ParseResumePdfSkill`
- **`backend/scoring/scorer.py`** — Multi-dimensional job scorer: skills (40%), experience (25%), salary (20%), location (15%); uses sentence-transformers locally (~470MB, `paraphrase-multilingual-MiniLM-L12-v2`)
- **`backend/automation/`** — Patchright (undetected Playwright) wrappers; browser is a singleton with persistent cookies
- **`backend/core/config.py`** — All config via Pydantic Settings (env vars); `LLM_API_KEY` falls back to `DEEPSEEK_API_KEY`
- **`backend/core/settings_store.py`** — Reads/writes `agent_settings.json` at runtime; API can hot-swap strategy config without restart

### Database

SQLite with WAL mode (`data/jobs.db`). Three tables:
- **`Job`** — scraped listings; status lifecycle: `PENDING → MATCHED → APPROVED → PENDING_SEND → SENT`
- **`Application`** — per-send records; status: `APPROVED → SENT → READ → REPLIED`
- **`ResumeSnapshot`** — versioned resume snapshots linked to each application

Schema migrations are handled manually via `ALTER TABLE` in `db/engine.py` on startup.

### Frontend Structure

Next.js 14 app directory (`frontend/app/`). Pages: dashboard (`/`), jobs (`/jobs`), apply (`/apply`), records, settings, profile, chat, analytics. Uses shadcn/ui (Radix UI) + Tailwind CSS. The `NEXT_PUBLIC_API_URL` env var points to the backend.

### LLM Integration

- LLM calls use LangChain with any OpenAI-compatible API (configured via `LLM_BASE_URL`; defaults to DeepSeek).
- **`backend/agent/hermes_agent.py`** — Claude tool-use agent for natural language control via `/agent/hermes`
- **`backend/agents/resume_agent.py`** — 3-phase resume adaptation: extract JD keywords → rank profile items → rewrite bullet points only
- **`backend/agents/message_agent.py`** — Generates ~120-char personalized opening messages

## Key Design Constraints

- **Windows**: Always use `python run.py` (not `uvicorn` directly) because Patchright requires `ProactorEventLoop` on Windows.
- **Human approval gate**: Jobs must be `APPROVED` before any application is sent. The frontend UI is the approval interface.
- **Cooldown queue**: Approved jobs wait in `PENDING_SEND` until cooldown expires; the scheduler flushes every 5 min.
- **Daily apply limit**: Enforced in `ApplyJobSkill`; default 30/day. Gaussian-distributed delays between sends simulate human behavior.
- **Selectors**: BOSS 直聘 CSS selectors are stored in `data/selectors.json`, not hardcoded, to ease maintenance when the site changes.
- **Embedding model**: Downloaded once locally; set `HF_HUB_OFFLINE=1` in `.env` to prevent network calls after first download.
