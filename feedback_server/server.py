"""
Feedback server for the personal-development-journal.

Deployed on Railway (or any WSGI host). Handles the thumbs-up / thumbs-down
links embedded in the daily journal email.

Environment variables required:
  FEEDBACK_TOKEN   — shared secret that must be present in the ?token= param
  GH_PAT           — GitHub Personal Access Token with `contents:write` scope
  GH_REPO          — owner/repo  (e.g. "kghamilton89/personal-development-journal")
  GH_BRANCH        — branch to commit to (default: "main")
  FEEDBACK_CSV_PATH — path inside the repo (default: "data/feedback.csv")
  PORT             — port to listen on (Railway sets this automatically)
"""

import base64
import csv
import io
import os
import re
from datetime import datetime, timezone

import requests
from flask import Flask, Response, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
VALID_RATINGS = {"up", "down"}
# Allowlist for question IDs: ISO-8601 timestamp slugs, e.g. 2026-03-10T00-19-39Z
_ID_RE = re.compile(r"^[\w\-:\.]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _must(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {_must('GH_PAT')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file(repo: str, path: str, branch: str):
    """Return (content_bytes, sha) for a file in the repo, or (None, None) if missing."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_gh_headers(), params={"ref": branch}, timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    raw = base64.b64decode(data["content"])
    return raw, data["sha"]


def _put_file(
    repo: str,
    path: str,
    branch: str,
    content_bytes: bytes,
    sha: str | None,
    message: str,
) -> None:
    """Create or update a file in the repo via the GitHub Contents API."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    body: dict = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=_gh_headers(), json=body, timeout=15)
    r.raise_for_status()


def _append_feedback(question_id: str, rating: str, rated_at: str) -> None:
    """Read feedback.csv from GitHub, append a row, write it back."""
    repo = _must("GH_REPO")
    branch = os.getenv("GH_BRANCH", "main")
    csv_path = os.getenv("FEEDBACK_CSV_PATH", "data/feedback.csv")

    raw, sha = _get_file(repo, csv_path, branch)

    # Parse existing CSV or start fresh.
    if raw:
        text = raw.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    else:
        rows = []

    # If there is already a row for this question_id, just update the rating.
    existing = next(
        (row for row in rows if row.get("question_id") == question_id), None
    )
    if existing:
        existing["rating"] = rating
        existing["rated_at"] = rated_at
    else:
        rows.append(
            {"question_id": question_id, "rating": rating, "rated_at": rated_at}
        )

    # Serialise back.
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["question_id", "rating", "rated_at"])
    writer.writeheader()
    writer.writerows(rows)
    new_bytes = buf.getvalue().encode("utf-8")

    _put_file(
        repo,
        csv_path,
        branch,
        new_bytes,
        sha,
        f"feedback: {rating} for {question_id}",
    )


# ---------------------------------------------------------------------------
# Response pages
# ---------------------------------------------------------------------------

_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      background:#0f0f13;font-family:system-ui,sans-serif;color:#e2e2e9;
    }}
    .card{{
      background:#1a1a24;border:1px solid #2e2e42;border-radius:16px;
      padding:48px 56px;text-align:center;max-width:420px;
    }}
    .icon{{font-size:3rem;margin-bottom:20px}}
    h1{{font-size:1.4rem;font-weight:600;margin-bottom:10px}}
    p{{font-size:.95rem;color:#8888aa;line-height:1.6}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{body}</p>
  </div>
</body>
</html>"""


def _html_response(title: str, icon: str, body: str, status: int = 200) -> Response:
    html = _PAGE.format(title=title, icon=icon, body=body)
    return Response(html, status=status, mimetype="text/html")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/feedback")
def feedback():
    # --- Validate token ---
    expected_token = os.getenv("FEEDBACK_TOKEN", "")
    if not expected_token or request.args.get("token") != expected_token:
        return _html_response("Not authorised", "🔒", "Invalid or missing token.", 403)

    # --- Validate inputs ---
    question_id = request.args.get("id", "").strip()
    rating = request.args.get("rating", "").strip().lower()

    if not question_id or not _ID_RE.match(question_id):
        return _html_response(
            "Bad request", "⚠️", "Missing or invalid question ID.", 400
        )

    if rating not in VALID_RATINGS:
        return _html_response("Bad request", "⚠️", "Rating must be 'up' or 'down'.", 400)

    # --- Write feedback ---
    rated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        _append_feedback(question_id, rating, rated_at)
    except Exception as exc:
        app.logger.error("Failed to write feedback: %s", exc)
        return _html_response(
            "Something went wrong",
            "❌",
            "Could not save your feedback. Please try again later.",
            500,
        )

    # --- Success ---
    if rating == "up":
        return _html_response(
            "Thanks for the thumbs up!",
            "👍",
            "Good to know — more like this is on the way.",
        )
    else:
        return _html_response(
            "Noted.",
            "👎",
            "Feedback recorded — the next question will aim higher.",
        )


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point (local dev)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
