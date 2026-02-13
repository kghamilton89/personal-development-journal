import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import requests
from openai import OpenAI


BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def must_getenv(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def load_history(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Create an empty file.
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


def build_instructions() -> str:
    return (
        "You generate ONE daily journaling question.\n\n"
        "The question must be written in FIVE languages in the following order:\n"
        "1. Serbian (Latin script)\n"
        "2. Turkish\n"
        "3. French\n"
        "4. Russian\n"
        "5. English\n\n"
        "Formatting rules:\n"
        "- Each language must appear on its own line.\n"
        "- No bullet points, no numbering, no labels.\n"
        "- Output only the five questions, nothing else.\n"
        "- Each line must be a single sentence ending with '?'.\n"
        "- The content across languages must be semantically equivalent.\n\n"
        "Content constraints:\n"
        "- Themes: self-actualization, philosophy, disciplined execution, long-term goals.\n"
        "- Must be intellectually serious and specific.\n"
        "- Avoid therapy clichés and motivational fluff.\n"
        "- Avoid repeating prior structure or wording.\n"
        "- Maintain long-term conceptual progression across days.\n"
    )


def build_context(history_tail: List[Dict[str, Any]]) -> str:
    """
    Provide the model with a compact view of recent questions.
    We store multi-language blocks; show only the English line when available
    (5th line), otherwise show the raw question text.
    """
    lines: List[str] = []

    for item in history_tail:
        q = (item.get("question") or "").strip()
        d = (item.get("date_utc") or "").strip()
        if not q:
            continue

        # If q is 5 lines, try to extract the English line (5th).
        q_lines = [x.strip() for x in q.splitlines() if x.strip()]
        if len(q_lines) >= 5:
            q_show = q_lines[4]
        else:
            q_show = " ".join(q.split())

        lines.append(f"- [{d}] {q_show}")

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
    - remove empty lines
    - ensure exactly 5 non-empty lines
    - ensure each ends with '?'
    - ensure no extra text
    """
    raw_lines = [ln.strip() for ln in (text or "").splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]

    # If the model returned more than 5 lines, keep first 5 meaningful lines.
    if len(raw_lines) > 5:
        raw_lines = raw_lines[:5]

    # If fewer than 5 lines, it's invalid.
    if len(raw_lines) != 5:
        raise RuntimeError(
            f"Model output must contain exactly 5 non-empty lines; got {len(raw_lines)}.\nOutput:\n{text}"
        )

    fixed: List[str] = []
    for ln in raw_lines:
        # collapse internal whitespace
        ln = " ".join(ln.split())
        if not ln.endswith("?"):
            ln = ln.rstrip(".") + "?"
        # If multiple question marks, keep up to first '?'
        if ln.count("?") > 1:
            ln = ln.split("?")[0].strip() + "?"
        fixed.append(ln)

    return "\n".join(fixed)


def generate_question(history_tail: List[Dict[str, Any]]) -> str:
    client = OpenAI(api_key=must_getenv("OPENAI_API_KEY"))

    instructions = build_instructions()
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


def append_history(path: str, date_utc: str, question: str) -> None:
    record = {"date_utc": date_utc, "question": question}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def send_via_brevo(subject: str, text_body: str) -> None:
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
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }

    r = requests.post(BREVO_SEND_URL, headers=headers, json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Brevo API error {r.status_code}: {r.text}")


def human_date_moscow() -> str:
    """
    Render date as: "13 February, 2026" in Europe/Moscow timezone.
    """
    msk = ZoneInfo("Europe/Moscow")
    now = datetime.now(msk)
    # Day without leading zero on Linux: %-d; on Windows it's %#d.
    # GitHub Actions runners are Linux, so %-d is safe here.
    return now.strftime("%-d %B, %Y")


def main() -> None:
    history_path = os.getenv("HISTORY_PATH", "data/journal_questions.jsonl")
    history_tail_n = int(os.getenv("HISTORY_TAIL", "120"))

    history = load_history(history_path)
    recent = tail_history(history, history_tail_n)

    question_block = generate_question(recent)

    now_utc = datetime.now(timezone.utc)
    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    append_history(history_path, ts_utc, question_block)

    subject_prefix = os.getenv("SUBJECT_PREFIX", "Daily Journal Question")
    date_human = human_date_moscow()
    subject = f"{subject_prefix} — {date_human}"

    # Email body is exactly the 5 lines.
    body = question_block + "\n"

    send_via_brevo(subject=subject, text_body=body)


if __name__ == "__main__":
    main()