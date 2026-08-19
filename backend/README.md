# InboxIQ — Backend (API)

Flask JSON API that powers InboxIQ: email summarization, sentiment (Gemini +
VADER hybrid), priority detection, action-item extraction, and optional
IMAP inbox fetching. Pair this with the sibling `frontend/` project (or any
client of your choosing).

## Run locally

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your Gemini API key (https://aistudio.google.com/apikey)

python app.py
# API now running at http://localhost:5000
```

Verify it's up:

```bash
curl http://localhost:5000/api/health
```

## Deploy on Render

1. Push this `backend/` folder to a GitHub repo (or push the whole
   `inboxiq/` monorepo and set Render's **Root Directory** to `backend`).
2. In Render: **New → Web Service**, connect the repo.
3. Settings:
   - **Root directory:** `backend` (only needed if using the monorepo)
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app`
4. Environment variables:
   - `GEMINI_API_KEY` = your key (free, no card needed)
   - `GEMINI_MODEL` = `gemini-2.5-flash` (optional, this is the default)
5. Deploy. Copy the resulting URL (e.g. `https://inboxiq-backend.onrender.com`)
   — you'll paste this into the frontend's `js/config.js`.

A `render.yaml` Blueprint is included if you'd rather deploy via **New →
Blueprint** and point it at this folder.

## CORS

`flask-cors` is enabled with permissive defaults so the separately-hosted
frontend can call this API. Before a real launch, lock it down in `app.py`:

```python
CORS(app, origins=["https://your-frontend-domain.com"])
```

## API reference

| Method | Route                  | Purpose                                     |
|--------|-------------------------|----------------------------------------------|
| GET    | `/`                      | API info                                      |
| GET    | `/api/health`             | Health check + whether the AI key is set       |
| GET    | `/api/demo-inbox`          | Sample inbox previews                          |
| POST   | `/api/summarize`           | Analyze one email `{sender, subject, body}`    |
| POST   | `/api/summarize-batch`     | Analyze a list of emails at once               |
| POST   | `/api/connect-inbox`       | Fetch recent emails via IMAP app password      |

### Example: `POST /api/summarize`

```json
{
  "sender": "Priya Nair <priya@company.com>",
  "subject": "Re: Q3 migration — need sign-off",
  "body": "Hi team, following up on last week's call..."
}
```

Response:

```json
{
  "tldr": "...",
  "summary": "...",
  "key_points": ["..."],
  "action_items": ["..."],
  "sentiment": "neutral",
  "sentiment_reason": "...",
  "priority": "urgent",
  "priority_reason": "...",
  "category": "Engineering",
  "requires_reply": true,
  "estimated_read_time_saved_seconds": 45,
  "vader": { "compound": 0.0, "label": "neutral" },
  "original_word_count": 210,
  "processing_time_ms": 1830
}
```

## IMAP "connect real inbox" notes

Uses an **app password**, not OAuth, so there's no Google/Microsoft app
review process. Nothing is stored server-side — the password is used only
for the duration of the request. For Gmail: Google Account → Security →
2-Step Verification → App passwords.
