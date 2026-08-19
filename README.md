# InboxIQ — AI Email Summarizer

Turns long, messy emails into a short, scannable briefing: a one-line TL;DR,
key points, action items, sentiment, and a priority stamp — powered by
Google Gemini (a free-tier API, no card required) with a lightweight VADER sentiment pass as a fast,
independent cross-check ("hybrid AI" pipeline). Built for a hackathon.

This repo is split into two independently deployable pieces:

```
inboxiq/
├── backend/    → Flask JSON API (Python) — does the AI analysis
└── frontend/   → Static HTML/CSS/JS dashboard — talks to the backend
```

Each folder has its own README with full setup and deploy instructions.
Quick start:

## 1. Run the backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your GEMINI_API_KEY into .env
python app.py              # -> http://localhost:5000
```

## 2. Run the frontend

```bash
cd frontend
# js/config.js already points at http://localhost:5000 by default
python -m http.server 8080   # -> http://localhost:8080
```

Open `http://localhost:8080` — the dashboard will call the backend
automatically.

## Features

- **AI summarization** — plain-language summary + one-sentence TL;DR
- **Sentiment analysis** — Gemini's contextual read *and* a VADER
  lexicon-based score, shown side by side
- **Priority stamp** — urgent / high / normal / low, with reasoning
- **Action item extraction** — a checkable list of concrete next steps
- **Category tagging** — Finance, HR, Sales, Security, etc.
- **Time-saved counter** — running total of reading time saved this session
- **Three ways to try it**: a built-in demo inbox, pasting any email, or
  connecting a real inbox via IMAP app password (Gmail/Outlook/Yahoo/iCloud)

## Deploying both to Render

Deploy them as **two separate Render services** from this one repo:

1. **Backend** — New → Web Service → Root Directory: `backend`
   (Build: `pip install -r requirements.txt`, Start: `gunicorn app:app`,
   env var `GEMINI_API_KEY`).
2. **Frontend** — New → Static Site → Root Directory: `frontend`
   (Build: empty, Publish directory: `.`).
3. Copy the backend's live URL into `frontend/js/config.js`
   (`window.API_BASE_URL = "https://your-backend.onrender.com"`), commit,
   push. Render auto-redeploys the frontend.

Each folder's own `render.yaml` lets you deploy it as a Blueprint too.

## Tech stack

| Layer      | Choice                                              |
|------------|------------------------------------------------------|
| Backend    | Flask, gunicorn, flask-cors                            |
| AI         | Google Gemini API (`google-genai` Python SDK)          |
| NLP extra  | `vaderSentiment` (rule-based sentiment cross-check)    |
| Inbox sync | `imaplib` (stdlib) — no OAuth app review needed        |
| Frontend   | Static HTML/CSS/JS, no build step, no framework        |
| Hosting    | Render (Web Service + Static Site, free tier friendly) |

## Notes for the demo

- Get a free Gemini API key (no credit card needed) at https://aistudio.google.com/apikey
- The free Render plan spins down after inactivity — the first request
  after idling can take ~30–50 seconds. Open the app a minute before
  presenting.
- The IMAP "connect real inbox" feature uses an app password, not OAuth,
  so there's nothing to get approved before your deadline.

## Ideas for extending this further

- Persist analyzed emails per user (Postgres on Render)
- Daily digest email of the top 5 priority items
- Slack/Teams integration to post urgent summaries automatically
- VIP-sender / keyword-based priority overrides
- Multi-language summarization (just relay the user's preferred language
  in the backend prompt)
