# InboxIQ — Frontend

Static HTML/CSS/JS dashboard for InboxIQ. No build step, no framework —
just open `index.html` or deploy the folder as-is to any static host.

This talks to the `backend/` API (Flask). It does **not** work standalone —
start the backend first, then point this at it.

## Point it at your backend

Edit `js/config.js`:

```js
// Local development:
window.API_BASE_URL = "http://localhost:5000";

// After deploying the backend on Render:
window.API_BASE_URL = "https://inboxiq-backend.onrender.com";
```

## Run locally

Any static file server works. Easiest with Python (already installed if
you're running the backend too):

```bash
cd frontend
python -m http.server 8080
# open http://localhost:8080
```

Make sure `backend/app.py` is running at the URL set in `js/config.js`
(default: `http://localhost:5000`).

## Deploy on Render

1. Push this `frontend/` folder to GitHub (or push the whole `inboxiq/`
   monorepo and set Render's **Root Directory** to `frontend`).
2. In Render: **New → Static Site**, connect the repo.
3. Settings:
   - **Root directory:** `frontend` (only needed if using the monorepo)
   - **Build command:** *(leave empty)*
   - **Publish directory:** `.`
4. Before or after the first deploy, edit `js/config.js` to point at your
   deployed backend's URL, commit, and push — Render redeploys automatically.

A `render.yaml` Blueprint is included as an alternative to steps 2–3.

## Structure

```
frontend/
├── index.html
├── css/
│   └── style.css
├── js/
│   ├── config.js     # <- set your backend URL here
│   └── script.js
└── render.yaml
```

## Deploying frontend + backend together instead

If you'd rather run this as one Render Web Service (simpler for a quick
demo, single URL), it's easiest to use the combined single-service version
of this project instead of the split frontend/backend layout — happy to
provide that structure too if you'd prefer it.
