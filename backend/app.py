"""
InboxIQ — AI Email Summarizer
==============================
Backend API only. Serves JSON — pair it with the separate `frontend/`
static site (or any client) that calls these endpoints.

Endpoints
---------
GET  /                         -> API info / uptime check
GET  /api/health                -> health + whether the AI key is configured
GET  /api/demo-inbox             -> curated sample emails, for demos
POST /api/summarize              -> summarize ONE email (subject/sender/body)
POST /api/summarize-batch        -> summarize a LIST of emails at once
POST /api/connect-inbox          -> fetch real emails over IMAP (app password)
"""

import os
import re
import json
import time
import imaplib
import email
from email.header import decode_header
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors

load_dotenv()

# --------------------------------------------------------------------------
# App setup
# --------------------------------------------------------------------------
app = Flask(__name__)

# Allow the separately-hosted frontend to call this API. Lock this down to
# your actual frontend origin in production, e.g.:
#   CORS(app, origins=["https://your-frontend.onrender.com"])
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
vader = SentimentIntensityAnalyzer()

# --------------------------------------------------------------------------
# IMAP host lookup for a few common providers (used by /api/connect-inbox)
# --------------------------------------------------------------------------
IMAP_HOSTS = {
    "gmail": "imap.gmail.com",
    "outlook": "outlook.office365.com",
    "yahoo": "imap.mail.yahoo.com",
    "icloud": "imap.mail.me.com",
}

# --------------------------------------------------------------------------
# Demo inbox — lets judges try the product instantly, no credentials needed
# --------------------------------------------------------------------------
DEMO_EMAILS = [
    {
        "id": "demo-1",
        "sender": "Priya Nair <priya.nair@nimbuscloud.io>",
        "subject": "Re: Q3 infrastructure migration — need your sign-off by Friday",
        "date": "2026-08-15T09:14:00",
        "body": (
            "Hi team,\n\nFollowing up on last week's call about the Q3 infrastructure "
            "migration. After the vendor review, the platform team recommends moving "
            "forward with the phased migration plan (Option B) instead of the big-bang "
            "cutover we originally discussed. The main reasons are: (1) it lets us "
            "roll back individual services without downtime across the whole stack, "
            "(2) the cost delta is only about 4% higher over the first two quarters, "
            "and (3) our SRE team has more experience running phased migrations, which "
            "lowers operational risk significantly during a quarter where we already "
            "have the holiday freeze coming up.\n\nHowever, this does push our target "
            "completion date from September 30 to October 18, since we now need three "
            "migration waves instead of one. Finance has already asked whether this "
            "delay affects the Q4 budget forecast — it does not, since the total spend "
            "is roughly the same, just spread differently.\n\nI need a decision from "
            "you by end of day Friday so we can lock in the vendor's engineering slot "
            "for the first migration wave starting Monday. If I don't hear back by "
            "then, we'll default to the phased plan since that's the recommendation "
            "from both platform and SRE. Happy to jump on a call if you want to "
            "discuss trade-offs first.\n\nThanks,\nPriya"
        ),
    },
    {
        "id": "demo-2",
        "sender": "Marcus Webb <m.webb@brightpeakcapital.com>",
        "subject": "Frustrated — third time asking about the invoice discrepancy",
        "date": "2026-08-15T11:02:00",
        "body": (
            "This is the third email I've sent about invoice #INV-88213. We were "
            "billed $4,200 but the signed statement of work clearly caps the monthly "
            "retainer at $3,500. I flagged this on August 2nd and again on August 9th "
            "and still have not received a corrected invoice or even an acknowledgment "
            "from your billing team. Our finance department is now asking me why we're "
            "paying more than the contract states, and honestly it's putting me in an "
            "awkward position internally.\n\nI need this resolved before our payment "
            "run on Friday, or we'll have to withhold payment until it's corrected, "
            "which I really don't want to do given how well the actual project work "
            "has been going. Can someone please just confirm the $700 will be credited "
            "and send over a corrected invoice today?"
        ),
    },
    {
        "id": "demo-3",
        "sender": "Aditi Sharma (People Team) <aditi.sharma@nimbuscloud.io>",
        "subject": "Open enrollment starts Monday + a few benefits updates",
        "date": "2026-08-14T16:45:00",
        "body": (
            "Hi everyone,\n\nJust a heads up that open enrollment for benefits opens "
            "this coming Monday, August 18th, and closes on September 5th. A few "
            "things changed this year that are worth knowing about before you pick a "
            "plan:\n\n1. We've added a new high-deductible health plan option paired "
            "with an HSA, and the company will now match HSA contributions up to $500 "
            "per year.\n2. The dental plan's orthodontia coverage increased from "
            "$1,500 to $2,500 lifetime max.\n3. Commuter benefits now cover e-bike "
            "and scooter rentals, not just transit passes.\n4. Enrollment is done "
            "entirely through the new benefits portal this year (link below) — the "
            "old paper forms are no longer accepted.\n\nThere will be two optional "
            "info sessions, one on Tuesday at 11am and one on Thursday at 4pm, if you "
            "want to ask questions live. Nothing is required from you if you're happy "
            "with your current plan and it's still offered, it will just roll over "
            "automatically. Let me know if you have questions.\n\nBest,\nAditi"
        ),
    },
    {
        "id": "demo-4",
        "sender": "GitHub <notifications@github.com>",
        "subject": "[nimbus/core-api] 4 new pull requests opened, 2 need your review",
        "date": "2026-08-15T07:30:00",
        "body": (
            "Activity summary for nimbus/core-api:\n\n"
            "- PR #482 'Fix race condition in webhook retry queue' by jchen — "
            "awaiting your review, marked urgent, touches production payment code.\n"
            "- PR #483 'Update dependency: requests 2.31 -> 2.32' by dependabot — "
            "auto-mergeable, low risk.\n"
            "- PR #484 'Add rate limiting to /v2/summarize endpoint' by t.okafor — "
            "awaiting your review, has 2 approving comments already.\n"
            "- PR #485 'Typo fixes in README' by contributor42 — no review needed.\n\n"
            "You also have 3 unresolved review comments on PR #479 from yesterday."
        ),
    },
    {
        "id": "demo-5",
        "sender": "Sarah Kim <sarah.kim@northstarventures.com>",
        "subject": "Loved the demo — let's talk next steps",
        "date": "2026-08-14T13:20:00",
        "body": (
            "Hi! I just wanted to say the product demo yesterday was genuinely "
            "impressive — the team was asking great follow-up questions afterward, "
            "which is always a good sign. A couple of us think this could be a strong "
            "fit for our seed-stage portfolio thesis around workplace productivity "
            "tools.\n\nWould you be open to a follow-up call next week with our full "
            "partner group? We'd want to dig a bit deeper into your retention numbers "
            "and roadmap for the next two quarters. No pressure at all if the timing "
            "isn't right — just genuinely excited about what you're building and "
            "wanted to keep the conversation going while it's fresh.\n\nLet me know "
            "what works, Tuesday or Wednesday afternoon are both good on our end.\n\n"
            "Best,\nSarah"
        ),
    },
    {
        "id": "demo-6",
        "sender": "IT Security <security-alerts@nimbuscloud.io>",
        "subject": "ACTION REQUIRED: Your password expires in 3 days",
        "date": "2026-08-15T06:00:00",
        "body": (
            "This is an automated reminder that your corporate account password will "
            "expire in 3 days on August 18, 2026. To avoid being locked out of email, "
            "VPN, and internal tools, please update your password before then using "
            "the self-service portal at password.nimbuscloud.io. Passwords must be at "
            "least 14 characters and cannot match any of your last 10 passwords. If "
            "you're locked out after expiration, contact the IT helpdesk at "
            "ext. 4400."
        ),
    },
]

# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the analysis engine inside InboxIQ, a professional email \
summarization product. Given a single email, you extract a compact, accurate, \
skimmable briefing for a busy professional.

Always respond with ONLY a single valid JSON object — no markdown fences, no \
preamble, no commentary outside the JSON. Use exactly this schema:

{
  "tldr": "one sentence, max ~25 words, the single most important takeaway",
  "summary": "2-4 sentence plain-language summary of the email body",
  "key_points": ["short bullet", "short bullet", "..."],
  "action_items": ["specific action the recipient should take, or empty array if none"],
  "sentiment": "positive" | "neutral" | "negative" | "mixed",
  "sentiment_reason": "one short clause explaining the sentiment call",
  "priority": "urgent" | "high" | "normal" | "low",
  "priority_reason": "one short clause explaining the priority call",
  "category": "one or two words, e.g. 'Finance', 'HR', 'Sales', 'Engineering', 'Security', 'Newsletter', 'Personal'",
  "requires_reply": true | false,
  "estimated_read_time_saved_seconds": integer
}

Guidelines:
- key_points: 2-5 items max, each under 15 words, no fluff.
- action_items: only concrete, actionable next steps explicitly implied by the email. Empty array if it's purely informational.
- priority "urgent" = time-boxed deadline or explicit escalation/frustration; "high" = important but not time-critical today; "normal" = standard business email; "low" = FYI/automated/newsletter.
- Never invent facts not present in the email.
- estimated_read_time_saved_seconds: rough estimate of reading time saved by reading your summary instead of the full email (assume ~200 words/minute reading speed for the original)."""


def build_user_prompt(sender: str, subject: str, body: str) -> str:
    return (
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"---\n"
        f"{body}\n"
        f"---\n"
        f"Analyze this email and return the JSON object described in your instructions."
    )


def call_gemini(sender: str, subject: str, body: str) -> dict:
    """Call the Gemini API and parse the structured JSON response."""
    if client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured on the server. "
            "Set it as an environment variable to enable AI summarization."
        )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=build_user_prompt(sender, subject, body),
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",  # ask Gemini to return raw JSON
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    # If generation was cut off (e.g. hit the token limit) or blocked, response.text
    # can be empty or raise. Surface a clear, specific error instead of a bare
    # JSONDecodeError so it's obvious what went wrong.
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        finish_reason = getattr(candidates[0], "finish_reason", None)
        finish_reason_name = getattr(finish_reason, "name", str(finish_reason))
        if finish_reason_name not in ("STOP", "None", None):
            raise RuntimeError(
                f"Gemini stopped generating early ({finish_reason_name}). "
                "Try again, or try a shorter email body."
            )

    try:
        raw_text = (response.text or "").strip()
    except Exception:
        raw_text = ""

    if not raw_text:
        raise RuntimeError("Gemini returned an empty response. Please try again.")

    # Defensive cleanup in case the model wraps the JSON in a code fence
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback: extract the outermost {...} block in case of stray
        # leading/trailing text and retry once before giving up.
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def vader_signal(body: str) -> dict:
    """Fast, non-LLM sentiment cross-check used as a secondary confidence signal."""
    scores = vader.polarity_scores(body)
    compound = scores["compound"]
    if compound >= 0.3:
        label = "positive"
    elif compound <= -0.3:
        label = "negative"
    else:
        label = "neutral"
    return {"compound": round(compound, 3), "label": label}


def analyze_email(sender: str, subject: str, body: str) -> dict:
    ai_result = call_gemini(sender, subject, body)
    ai_result["vader"] = vader_signal(body)
    word_count = len(body.split())
    ai_result["original_word_count"] = word_count
    ai_result["original_read_time_seconds"] = round((word_count / 200) * 60)
    return ai_result


# --------------------------------------------------------------------------
# IMAP helpers
# --------------------------------------------------------------------------
def _decode(value):
    if value is None:
        return ""
    parts = decode_header(value)
    decoded = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded += text.decode(enc or "utf-8", errors="ignore")
        else:
            decoded += text
    return decoded


def _extract_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return ""


def fetch_recent_emails(imap_host: str, email_address: str, app_password: str, limit: int = 10):
    conn = imaplib.IMAP4_SSL(imap_host)
    try:
        conn.login(email_address, app_password)
        conn.select("INBOX")
        status, data = conn.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("Could not read inbox.")

        ids = data[0].split()[-limit:]
        ids.reverse()

        results = []
        for msg_id in ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            results.append(
                {
                    "id": msg_id.decode(),
                    "sender": _decode(msg.get("From")),
                    "subject": _decode(msg.get("Subject")) or "(no subject)",
                    "date": msg.get("Date", ""),
                    "body": _extract_body(msg)[:8000],  # cap body size sent to the model
                }
            )
        return results
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return jsonify(
        {
            "service": "InboxIQ API",
            "status": "running",
            "docs": "See README.md for the full endpoint list.",
            "frontend": "This is the backend API only — run the separate frontend/ project to use the UI.",
        }
    )


@app.route("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "ai_configured": client is not None,
            "ai_provider": "Google Gemini",
            "model": MODEL_NAME,
            "time": datetime.utcnow().isoformat(),
        }
    )


@app.route("/api/demo-inbox")
def demo_inbox():
    # Return lightweight previews only — full body is fetched on summarize.
    previews = [
        {
            "id": e["id"],
            "sender": e["sender"],
            "subject": e["subject"],
            "date": e["date"],
            "preview": e["body"][:120].replace("\n", " ") + "…",
        }
        for e in DEMO_EMAILS
    ]
    return jsonify({"emails": previews})


@app.route("/api/summarize", methods=["POST"])
def summarize():
    payload = request.get_json(force=True, silent=True) or {}

    email_id = payload.get("id")
    sender = payload.get("sender", "").strip()
    subject = payload.get("subject", "").strip()
    body = payload.get("body", "").strip()

    # Allow re-summarizing a demo email by id without resending the body
    if email_id and not body:
        match = next((e for e in DEMO_EMAILS if e["id"] == email_id), None)
        if match:
            sender, subject, body = match["sender"], match["subject"], match["body"]

    if not body:
        return jsonify({"error": "Email body is required."}), 400

    try:
        start = time.time()
        result = analyze_email(sender or "Unknown sender", subject or "(no subject)", body)
        result["processing_time_ms"] = round((time.time() - start) * 1000)
        result["id"] = email_id
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except json.JSONDecodeError:
        return jsonify({"error": "The AI response could not be parsed. Please try again."}), 502
    except genai_errors.APIError as exc:
        return jsonify({"error": f"Gemini API error: {exc}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Unexpected error: {exc}"}), 500


@app.route("/api/summarize-batch", methods=["POST"])
def summarize_batch():
    payload = request.get_json(force=True, silent=True) or {}
    emails = payload.get("emails", [])
    if not isinstance(emails, list) or not emails:
        return jsonify({"error": "Provide a non-empty 'emails' list."}), 400

    results = []
    for item in emails[:20]:  # safety cap
        sender = item.get("sender", "Unknown sender")
        subject = item.get("subject", "(no subject)")
        body = item.get("body", "")
        email_id = item.get("id")
        if not body:
            continue
        try:
            analysis = analyze_email(sender, subject, body)
            analysis["id"] = email_id
            results.append(analysis)
        except Exception as exc:  # noqa: BLE001
            results.append({"id": email_id, "error": str(exc)})

    return jsonify({"results": results})


@app.route("/api/connect-inbox", methods=["POST"])
def connect_inbox():
    payload = request.get_json(force=True, silent=True) or {}
    provider = payload.get("provider", "gmail").lower()
    email_address = payload.get("email", "").strip()
    app_password = payload.get("app_password", "").strip()
    limit = min(int(payload.get("limit", 10)), 25)

    if not email_address or not app_password:
        return jsonify({"error": "Email and app password are required."}), 400

    host = IMAP_HOSTS.get(provider)
    if not host:
        return jsonify({"error": f"Unsupported provider '{provider}'."}), 400

    try:
        emails = fetch_recent_emails(host, email_address, app_password, limit=limit)
        previews = [
            {
                "id": e["id"],
                "sender": e["sender"],
                "subject": e["subject"],
                "date": e["date"],
                "body": e["body"],
                "preview": e["body"][:120].replace("\n", " ") + "…",
            }
            for e in emails
        ]
        return jsonify({"emails": previews})
    except imaplib.IMAP4.error as exc:
        return jsonify({"error": f"IMAP login failed: {exc}. Check your email/app password."}), 401
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Could not connect to inbox: {exc}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
