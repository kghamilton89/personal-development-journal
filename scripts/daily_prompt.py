import csv
import json
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

import requests
from openai import OpenAI


BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

# Canonical language definitions — name used in instructions + display label.
LANGUAGES = [
    {"code": "serbian", "instruction": "Serbian (Cyrillic script)", "label": "Српски"},
    {"code": "turkish", "instruction": "Turkish", "label": "Türkçe"},
    {"code": "french", "instruction": "French", "label": "Français"},
    {"code": "russian", "instruction": "Russian", "label": "Русский"},
]

LANGUAGE_CODES = [lang["code"] for lang in LANGUAGES]


def must_getenv(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
# Language-cycle state helpers
# ---------------------------------------------------------------------------


def _state_path(history_path: str) -> str:
    """Derive the language-state file path from the history file path."""
    base, _ = os.path.splitext(history_path)
    return base + "_lang_state.json"


def load_language_state(history_path: str) -> List[str]:
    """
    Load the current language queue from disk.

    The queue is an ordered list of language codes that have NOT yet been
    used in the current cycle.  When the queue is empty (or the file does
    not exist), a fresh shuffled queue is created and returned.
    """
    path = _state_path(history_path)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            queue = data.get("queue", [])
            # Validate: must be a subset of known language codes.
            if isinstance(queue, list) and all(c in LANGUAGE_CODES for c in queue):
                return queue
        except (json.JSONDecodeError, KeyError):
            pass  # Fall through to create a fresh queue.

    return _new_shuffled_queue()


def save_language_state(history_path: str, queue: List[str]) -> None:
    """Persist the updated queue to disk."""
    path = _state_path(history_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"queue": queue}, f, ensure_ascii=False)


def _new_shuffled_queue() -> List[str]:
    """Return all five language codes in a new random order."""
    codes = list(LANGUAGE_CODES)
    random.shuffle(codes)
    return codes


def pick_language(history_path: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Pop the next language from the cycle queue and return it together with
    the updated (remaining) queue.

    When the queue becomes empty after popping, a new shuffled queue is
    created immediately so it is ready for the next call — but it is NOT
    saved here; `save_language_state` must be called by the caller.
    """
    queue = load_language_state(history_path)
    chosen_code = queue.pop(0)

    # Replenish when exhausted.
    if not queue:
        queue = _new_shuffled_queue()

    lang = next(
        lang_entry for lang_entry in LANGUAGES if lang_entry["code"] == chosen_code
    )
    return lang, queue


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


def load_history(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
        return []

    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def tail_history(history: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    if n <= 0:
        return []
    return history[-n:]


def append_history(
    path: str, date_utc: str, question: str, language_code: str, question_id: str
) -> None:
    record = {
        "date_utc": date_utc,
        "question_id": question_id,
        "question": question,
        "language": language_code,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Feedback helpers
# ---------------------------------------------------------------------------


def _feedback_path(history_path: str) -> str:
    """Derive the feedback CSV path from the history file path."""
    return os.path.join(os.path.dirname(history_path) or ".", "feedback.csv")


def load_feedback(history_path: str) -> Dict[str, str]:
    """
    Load feedback.csv and return a dict mapping question_id -> rating ("up"|"down").
    Returns an empty dict if the file does not exist yet.
    """
    path = _feedback_path(history_path)
    if not os.path.exists(path):
        return {}
    result: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = (row.get("question_id") or "").strip()
            rating = (row.get("rating") or "").strip().lower()
            if qid and rating in {"up", "down"}:
                result[qid] = rating
    return result


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def build_instructions(
    lang: Dict[str, str], feedback: Dict[str, str], history: List[Dict[str, Any]]
) -> str:
    """
    Build the system instructions, including any feedback signal derived from
    the user's thumbs-up / thumbs-down ratings on past questions.
    """
    # Build a lookup of question_id -> question text for rated items.
    id_to_question: Dict[str, str] = {
        item["question_id"]: item["question"]
        for item in history
        if item.get("question_id") and item.get("question")
    }

    liked: List[str] = []
    disliked: List[str] = []
    for qid, rating in feedback.items():
        text = id_to_question.get(qid)
        if not text:
            continue
        if rating == "up":
            liked.append(text)
        else:
            disliked.append(text)

    feedback_block = ""
    if liked or disliked:
        parts = ["\nUser feedback on past questions:\n"]
        if liked:
            parts.append(
                "Questions the user rated GOOD (👍) — replicate tone, depth, specificity:\n"
            )
            for q in liked[-10:]:
                parts.append(f"  + {q}\n")
        if disliked:
            parts.append(
                "Questions the user rated BAD (👎) — avoid this style, framing, or theme:\n"
            )
            for q in disliked[-10:]:
                parts.append(f"  - {q}\n")
        feedback_block = "".join(parts)

    return (
        f"You generate ONE daily journaling question written in {lang['instruction']} only.\n\n"
        "Formatting rules:\n"
        "- Output exactly ONE line.\n"
        "- No bullet points, no numbering, no labels, no language name.\n"
        "- The line must be a single sentence ending with '?'.\n\n"
        "Content constraints:\n"
        "- Draw from the following theme categories, cycling through them so that NO single\n"
        "  category dominates the sequence over any 7-day window:\n"
        "    1. Goals & disciplined execution — long-term aims, systems, trade-offs, leading\n"
        "       indicators, strategic assumptions.\n"
        "    2. Philosophy — metaphysics, epistemology, ethics as theory, logic, the examined\n"
        "       life; engage specific thinkers or schools of thought where apt.\n"
        "    3. Personal reflection — identity, memory, formative experiences, relationships,\n"
        "       values in practice, the gap between who you are and who you intend to be.\n"
        "    4. Historical counterfactuals — 'what if' questions about pivotal moments in\n"
        "       history, how contingency shapes outcomes, and what those alternatives reveal\n"
        "       about the present.\n"
        "    5. Intellectual curiosity — science, mathematics, language, ideas across\n"
        "       disciplines; questions that reward genuine inquiry rather than opinion.\n"
        "    6. Ethics & values in practice — concrete moral dilemmas, competing obligations,\n"
        "       the cost of principles, integrity under pressure.\n"
        "    7. Creativity & meaning — aesthetics, craft, narrative, what makes work\n"
        "       meaningful, the relationship between making things and living well.\n"
        "- Must be intellectually serious and specific — no vague generalities.\n"
        "- Avoid therapy clichés, motivational fluff, and self-help platitudes.\n"
        "- Avoid repeating prior structure, framing, or wording.\n"
        "- Maintain long-term conceptual progression across days; treat the sequence as a\n"
        "  slow, cumulative intellectual journey rather than isolated daily prompts.\n"
        + feedback_block
    )


def build_context(history_tail: List[Dict[str, Any]]) -> str:
    """
    Provide the model with a compact view of recent questions.
    Each entry now also carries the language it was written in.
    """
    lines: List[str] = []

    for item in history_tail:
        q = (item.get("question") or "").strip()
        d = (item.get("date_utc") or "").strip()
        lang_code = item.get("language", "unknown")
        if not q:
            continue
        # Collapse any multi-line legacy entries to a single line.
        q_show = " | ".join(x.strip() for x in q.splitlines() if x.strip())
        lines.append(f"- [{d}] ({lang_code}) {q_show}")

    joined = "\n".join(lines) if lines else "(no prior questions yet)"
    return (
        "Here are previous journal questions (most recent last). "
        "Do NOT repeat them; continue the sequence.\n"
        f"{joined}\n"
    )


def normalize_output(text: str) -> str:
    """
    Normalize model output:
    - trim
    - expect exactly 1 non-empty line
    - ensure it ends with '?'
    """
    raw_lines = [ln.strip() for ln in (text or "").splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]

    # If the model returned more than 1 line, keep only the first.
    if len(raw_lines) > 1:
        raw_lines = raw_lines[:1]

    if len(raw_lines) != 1:
        raise RuntimeError(
            f"Model output must contain exactly 1 non-empty line; got {len(raw_lines)}.\nOutput:\n{text}"
        )

    ln = " ".join(raw_lines[0].split())
    if not ln.endswith("?"):
        ln = ln.rstrip(".") + "?"
    if ln.count("?") > 1:
        ln = ln.split("?")[0].strip() + "?"

    return ln


def generate_question(
    history_tail: List[Dict[str, Any]],
    lang: Dict[str, str],
    feedback: Dict[str, str],
    full_history: List[Dict[str, Any]],
) -> str:
    client = OpenAI(api_key=must_getenv("OPENAI_API_KEY"))

    instructions = build_instructions(lang, feedback, full_history)
    context = build_context(history_tail)

    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_input = (
        f"UTC date today: {today_utc}\n\n"
        f"{context}\n"
        "Now generate the next question in the sequence."
    )

    resp = client.responses.create(
        model="gpt-5.2",
        instructions=instructions,
        input=user_input,
    )

    return normalize_output(resp.output_text)


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------


def human_date_moscow() -> str:
    """
    Render date as: "13 February, 2026" in Europe/Moscow timezone.
    """
    msk = ZoneInfo("Europe/Moscow")
    now = datetime.now(msk)
    return now.strftime("%-d %B, %Y")


def _feedback_url(base_url: str, token: str, question_id: str, rating: str) -> str:
    """Build a feedback URL with all required parameters."""
    from urllib.parse import urlencode

    params = urlencode({"id": question_id, "rating": rating, "token": token})
    return f"{base_url.rstrip('/')}/feedback?{params}"


def format_email_content(
    question: str,
    lang: Dict[str, str],
    question_id: str,
    feedback_base_url: str,
    feedback_token: str,
) -> Tuple[str, str]:
    """
    Takes the normalized single-line question, the chosen language, and feedback
    link parameters, and produces:
      - text_content (plain text)
      - html_content (with thumbs-up / thumbs-down icon links)
    """
    date_line = human_date_moscow()

    url_up = _feedback_url(feedback_base_url, feedback_token, question_id, "up")
    url_down = _feedback_url(feedback_base_url, feedback_token, question_id, "down")

    # Plain-text fallback (no icons possible).
    text = (
        f"{date_line}\n"
        f"- {lang['label']}: {question}\n"
        f"\nWas this question useful?\n"
        f"  👍 Yes: {url_up}\n"
        f"  👎 No:  {url_down}\n"
    )

    html = f"""<div style="font-family: Arial, Helvetica, sans-serif; line-height: 1.5; color: #1a1a2e; max-width: 640px;">
  <div style="margin-bottom: 14px; font-size: 0.85rem; color: #6b6b8a; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;">{escape_html(date_line)}</div>
  <div style="font-size: 1.15rem; font-weight: 500; margin-bottom: 28px;">
    <span style="color: #6b6b8a; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;">{escape_html(lang['label'])}&nbsp;&nbsp;</span>{escape_html(question)}
  </div>
  <div style="border-top: 1px solid #e4e4f0; padding-top: 18px; display: flex; gap: 12px; align-items: center;">
    <span style="font-size: 0.78rem; color: #9999b3; margin-right: 6px;">Was this useful?</span>
    <a href="{url_up}"
       style="display: inline-flex; align-items: center; justify-content: center;
              width: 40px; height: 40px; border-radius: 50%;
              background: #f0fdf4; border: 1px solid #bbf7d0;
              font-size: 1.25rem; text-decoration: none; line-height: 1;"
       title="Good question">&#128077;</a>
    <a href="{url_down}"
       style="display: inline-flex; align-items: center; justify-content: center;
              width: 40px; height: 40px; border-radius: 50%;
              background: #fff1f2; border: 1px solid #fecdd3;
              font-size: 1.25rem; text-decoration: none; line-height: 1;"
       title="Not useful">&#128078;</a>
  </div>
</div>"""

    return text, html


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------


def send_via_brevo(subject: str, text_body: str, html_body: str) -> None:
    api_key = must_getenv("BREVO_API_KEY")

    payload = {
        "sender": {
            "name": must_getenv("BREVO_SENDER_NAME"),
            "email": must_getenv("BREVO_SENDER_EMAIL"),
        },
        "to": [
            {
                "name": must_getenv("BREVO_TO_NAME"),
                "email": must_getenv("BREVO_TO_EMAIL"),
            }
        ],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": html_body,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }

    r = requests.post(BREVO_SEND_URL, headers=headers, json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Brevo API error {r.status_code}: {r.text}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    history_path = os.getenv("HISTORY_PATH", "data/journal_questions.jsonl")
    history_tail_n = int(os.getenv("HISTORY_TAIL", "120"))
    feedback_base_url = os.getenv("FEEDBACK_BASE_URL", "")
    feedback_token = os.getenv("FEEDBACK_TOKEN", "")

    # 1. Determine today's language from the cycle.
    lang, remaining_queue = pick_language(history_path)

    # 2. Load full history (needed for feedback look-up) + tail for context.
    history = load_history(history_path)
    recent = tail_history(history, history_tail_n)

    # 3. Load user feedback on past questions.
    feedback = load_feedback(history_path)

    # 4. Generate question in the chosen language, informed by feedback.
    question = generate_question(recent, lang, feedback, history)

    # 5. Assign a stable ID for this question (used by the feedback links).
    now_utc = datetime.now(timezone.utc)
    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Use a URL-safe slug: replace colons with hyphens.
    question_id = ts_utc.replace(":", "-")

    # 6. Persist: history record + updated language queue.
    append_history(history_path, ts_utc, question, lang["code"], question_id)
    save_language_state(history_path, remaining_queue)

    # 7. Send email.
    subject_prefix = os.getenv("SUBJECT_PREFIX", "Daily Journal Question")
    date_human = human_date_moscow()
    subject = f"{subject_prefix} — {date_human}"

    text_body, html_body = format_email_content(
        question, lang, question_id, feedback_base_url, feedback_token
    )
    send_via_brevo(subject=subject, text_body=text_body, html_body=html_body)


if __name__ == "__main__":
    main()
