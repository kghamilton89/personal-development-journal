import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any

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
        with open(path, "w", encoding="utf-8") as f:
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
    return history[-n:] if n > 0 else []


def build_instructions() -> str:
    # This is the “system prompt” equivalent: stable constraints.
    return (
        "You generate ONE daily journaling question.\n"
        "Goals: self-actualization, personal development, philosophy, goal-setting, disciplined execution.\n"
        "Output ONLY the question (no preface, no bullet points, no quotes).\n"
        "Constraints:\n"
        "- Must be a single sentence ending with '?'.\n"
        "- Must be intellectually serious, specific, and actionable.\n"
        "- Avoid therapy clichés, motivational poster language, and generic prompts.\n"
        "- Avoid repeating themes, wording, or structure from prior questions.\n"
        "- Maintain a logical progression over time: occasionally introduce a concept, then revisit it later with a deeper twist.\n"
        "- Balance: identity/values, strategy, ethics, time allocation, tradeoffs, habits, fear/avoidance, and long-term vision.\n"
    )


def build_context(history_tail: List[Dict[str, Any]]) -> str:
    # Give the model the sequence (recent tail), so it can avoid repeats and build continuity.
    # Keep it compact.
    lines = []
    for item in history_tail:
        q = (item.get("question") or "").strip()
        d = (item.get("date_utc") or "").strip()
        if q:
            lines.append(f"- [{d}] {q}")
    joined = "\n".join(lines) if lines else "(no prior questions yet)"
    return (
        "Here are previous journal questions (most recent last). "
        "Do NOT repeat them; continue the sequence.\n"
        f"{joined}\n"
    )


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

    q = (resp.output_text or "").strip()
    q = " ".join(q.split())

    if not q.endswith("?"):
        q = q.rstrip(".") + "?"

    # Guardrails: ensure it’s one line and not multiple questions.
    if q.count("?") > 1:
        # Keep only up to the first '?'
        q = q.split("?")[0].strip() + "?"

    return q


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


def main() -> None:
    history_path = os.getenv("HISTORY_PATH", "data/journal_questions.jsonl")
    history_tail_n = int(os.getenv("HISTORY_TAIL", "120"))

    history = load_history(history_path)
    recent = tail_history(history, history_tail_n)

    question = generate_question(recent)

    now_utc = datetime.now(timezone.utc)
    date_utc = now_utc.strftime("%Y-%m-%d")
    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    append_history(history_path, ts_utc, question)

    subject_prefix = os.getenv("SUBJECT_PREFIX", "Daily Journal Question")
    subject = f"{subject_prefix} — {date_utc}"
    body = question + "\n"

    send_via_brevo(subject=subject, text_body=body)


if __name__ == "__main__":
    main()
