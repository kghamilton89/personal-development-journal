# Daily Journal Automation Workflow

This project automatically generates a **single daily personal development journaling question** and emails it to you every morning using:

- GitHub Actions (scheduler + runner)
- OpenAI API (question generation)
- Brevo (transactional email delivery)
- Railway (feedback endpoint)

The system:

- Rotates through **4 languages in a randomised, non-repeating cycle** (Serbian, Turkish, French, Russian)
- Maintains a historical log of all prior questions
- Feeds previous questions back to the model for continuity
- Learns from your 👍 / 👎 feedback to shape future questions
- Commits updated history and feedback to the repository automatically

---

## How It Works

1. GitHub Actions runs daily at **05:00 MSK (02:00 UTC)**
2. The script picks today's language from a shuffled 4-language cycle (no language repeats until all 4 have been used)
3. It loads recent question history and your feedback ratings
4. OpenAI generates the next question — guided by history, theme categories, and feedback
5. The question is emailed via Brevo with **👍 / 👎 feedback buttons**
6. Clicking a button hits the Railway server, which writes your rating to `data/feedback.csv`
7. Tomorrow's generation reads that feedback and adjusts accordingly
8. GitHub commits updated history, language state, and feedback automatically

---

## Languages and Cycle

Each day one language is chosen at random. Once all 4 have been used, the cycle resets with a new random order.

| Language | Script          |
| -------- | --------------- |
| Српски   | Serbian Cyrillic |
| Türkçe   | Turkish          |
| Français | French           |
| Русский  | Russian          |

---

## Repository Structure

```text
.github/workflows/journal_prompt.yml     # Daily scheduler
scripts/daily_prompt.py                  # Question generation + email
feedback_server/server.py                # Flask feedback endpoint (Railway)
feedback_server/requirements.txt         # Feedback server dependencies
data/journal_questions.jsonl             # Question history (auto-committed)
data/journal_questions_lang_state.json   # Language cycle state (auto-committed)
data/feedback.csv                        # Thumbs up/down ratings (auto-committed)
requirements.txt                         # Python dependencies
Procfile                                 # Railway start command
```

---

## Required Accounts

1. **GitHub** — runs the daily workflow
2. **OpenAI** — generates questions
3. **Brevo** — sends the email
4. **Railway** — hosts the feedback server

---

## Setup

### Step 1 — OpenAI API Key

1. Go to [platform.openai.com](https://platform.openai.com/) → **API Keys**
2. Create a new secret key
3. Add to GitHub as secret: `OPENAI_API_KEY`

---

### Step 2 — Brevo Transactional Email

1. Create an account at [brevo.com](https://www.brevo.com/)
2. Go to **Transactional → Settings → API Keys** and create a key
3. Add and verify a sender address under **Senders, Domains & Dedicated IPs**

Add these as GitHub Actions secrets:

| Secret               | Value                            |
| -------------------- | -------------------------------- |
| `BREVO_API_KEY`      | Your Brevo API key               |
| `BREVO_SENDER_EMAIL` | Verified sender address          |
| `BREVO_SENDER_NAME`  | Display name for the sender      |
| `BREVO_TO_EMAIL`     | Your email address               |
| `BREVO_TO_NAME`      | Your name                        |
| `SUBJECT_PREFIX`     | e.g. `Daily Prompt` (optional)   |

---

### Step 3 — Railway Feedback Server

The feedback server is a small Flask app that receives 👍/👎 clicks from your email and writes ratings to `data/feedback.csv` via the GitHub API.

#### A) Create a GitHub Fine-Grained PAT

1. GitHub → **Settings → Developer Settings → Fine-grained tokens**
2. New token with:
   - Repository: `personal-development-journal`
   - Permission: **Contents → Read and write**
3. Copy the token

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/q_cJ0H?referralCode=ozpZCF&utm_medium=integration&utm_source=template&utm_campaign=generic)

Use the link above to automatically deploy on Railway (recommended), or follow the steps below for a custom deployment.

#### B) Deploy on Railway

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select this repository
3. In the service → **Settings → Build & Deploy**, set:
   - **Start command**: `gunicorn --bind 0.0.0.0:$PORT feedback_server.server:app`
4. In the service → **Variables**, add:

| Variable             | Value                                        |
| -------------------- | -------------------------------------------- |
| `FEEDBACK_TOKEN`     | A long random secret (`openssl rand -hex 32`) |
| `GH_PAT`             | The PAT from step A                          |
| `GH_REPO`            | `kghamilton89/personal-development-journal`  |
| `GH_BRANCH`          | `main`                                       |
| `FEEDBACK_CSV_PATH`  | `data/feedback.csv`                          |

5. Go to **Settings → Networking → Generate Domain** and copy the URL

#### C) Add GitHub Secrets

| Secret               | Value                                        |
| -------------------- | -------------------------------------------- |
| `FEEDBACK_BASE_URL`  | `https://your-service.up.railway.app`        |
| `FEEDBACK_TOKEN`     | Same value as Railway's `FEEDBACK_TOKEN`     |

---

### Step 4 — Test the Workflow

1. Go to **Actions tab → Daily journaling question**
2. Click **Run workflow**
3. Confirm you receive an email with a question and 👍/👎 buttons
4. Click 👍 or 👎 in the email
5. Confirm `data/feedback.csv` appears in the repo

---

## All GitHub Actions Secrets

| Secret               | Purpose                        |
| -------------------- | ------------------------------ |
| `OPENAI_API_KEY`     | Question generation            |
| `BREVO_API_KEY`      | Email delivery                 |
| `BREVO_SENDER_EMAIL` | Sender address                 |
| `BREVO_SENDER_NAME`  | Sender display name            |
| `BREVO_TO_EMAIL`     | Recipient address              |
| `BREVO_TO_NAME`      | Recipient name                 |
| `SUBJECT_PREFIX`     | Email subject prefix           |
| `FEEDBACK_BASE_URL`  | Railway server URL             |
| `FEEDBACK_TOKEN`     | Shared secret for feedback auth |

---

## Customising Languages

The language pool is defined in two places. Both must be updated together whenever you add, remove, or change a language.

### 1. `scripts/daily_prompt.py` — the `LANGUAGES` list

Each entry needs three fields:

| Field | Purpose |
| ------------- | ----------------------------------------------- |
| `code` | Internal identifier (lowercase, no spaces) |
| `instruction` | Exact phrase passed to the model, e.g. `"Italian"` or `"Arabic (Modern Standard)"` |
| `label` | Native-script display name shown in the email, e.g. `"Italiano"` |

```python
LANGUAGES = [
    {"code": "serbian",  "instruction": "Serbian (Cyrillic script)", "label": "Српски"},
    {"code": "turkish",  "instruction": "Turkish",                   "label": "Türkçe"},
    {"code": "french",   "instruction": "French",                    "label": "Français"},
    {"code": "russian",  "instruction": "Russian",                   "label": "Русский"},
    # Add a new language like this:
    # {"code": "italian",  "instruction": "Italian",                 "label": "Italiano"},
]
```

### 2. `feedback_server/server.py` — the `RESPONSES` dict

Add a matching entry for every language code you add to `LANGUAGES`. Each entry needs translations for both the thumbs-up and thumbs-down thank-you page. The tuple format is `(html_lang_tag, title, body)`.

```python
RESPONSES = {
    ...
    # New entry matching the code in daily_prompt.py:
    "italian": {
        "up":   ("it", "Grazie per il pollice su!",  "Bene — ne arriveranno altre così."),
        "down": ("it", "Annotato.",                  "Feedback registrato — la prossima domanda punterà più in alto."),
    },
}
```

You can look up the correct `html_lang_tag` value for any language at [r12a.github.io/app-subtags](https://r12a.github.io/app-subtags/).

### 3. Reset the language cycle state

Whenever you change the language list, delete the old cycle state file so a clean queue is generated on the next run:

```bash
git rm --ignore-unmatch data/journal_questions_lang_state.json
git commit -m "chore: reset lang state after language change"
git push
```

If the file doesn't exist yet this command is a no-op — that's fine.

---

## Customising Prompt Behaviour

All prompt logic lives in `build_instructions()` in `scripts/daily_prompt.py`. The function constructs the system prompt that is sent to the model before every generation. You can edit it freely — no other file needs to change.

### Theme categories

The seven content themes are listed inline in `build_instructions()`. To add, remove, or reword a category, find this block and edit it directly:

```python
"- Draw from the following theme categories, cycling through them so that NO single\n"
"  category dominates the sequence over any 7-day window:\n"
"    1. Goals & disciplined execution — ...\n"
"    2. Philosophy — ...\n"
# Add or remove numbered entries here
```

Keep the numbering sequential and leave the cycling instruction intact, otherwise the model has no guidance on variety.

### Tone and style rules

The lines below the theme list control register and quality. Adjust them to suit your preferences:

```python
"- Must be intellectually serious and specific — no vague generalities.\n"
"- Avoid therapy clichés, motivational fluff, and self-help platitudes.\n"
"- Avoid repeating prior structure, framing, or wording.\n"
"- Maintain long-term conceptual progression across days...\n"
```

For example, to make questions more personal and less academic you might add:

```python
"- Favour questions grounded in lived experience over abstract theory.\n"
```

### How much history the model sees

The number of previous questions passed to the model as context is controlled by the `HISTORY_TAIL` environment variable (default: `120`). Set it in the GitHub Actions workflow or as a repo secret:

| Value | Effect |
| ----- | ------ |
| `30`  | Short memory — faster, lower token cost, less risk of repetition detection |
| `120` | Default — strong continuity and de-duplication across ~4 months |
| `365` | Long memory — most context, highest token cost |

### Feedback calibration wording

The paragraph that instructs the model how to interpret your 👍/👎 ratings is also in `build_instructions()`, inside the `feedback_block` construction. If you want the model to weight feedback more or less heavily, edit the framing text there.

---

## Changing the LLM

The model is called in `generate_question()` in `scripts/daily_prompt.py`. Swap the provider by replacing the client and API call — the rest of the pipeline (history, email, feedback) is completely decoupled from the model choice.

### What to change

**1. Install the new SDK** — add it to `requirements.txt`:

```text
# Example: replace or add alongside the existing openai entry
some-other-sdk>=1.0.0
```

**2. Replace the client and call** in `generate_question()`:

```python
# Current (OpenAI)
client = OpenAI(api_key=must_getenv("OPENAI_API_KEY"))
resp = client.responses.create(
    model="gpt-5.2",
    instructions=instructions,
    input=user_input,
)
return normalize_output(resp.output_text)

# Replace with your provider's equivalent, for example:
client = AnotherProviderClient(api_key=must_getenv("OTHER_API_KEY"))
resp = client.messages.create(
    model="their-model-name",
    system=instructions,
    messages=[{"role": "user", "content": user_input}],
    max_tokens=256,
)
return normalize_output(resp.content[0].text)
```

The exact method names and response shape vary by provider — consult their SDK docs.

**3. Update the API key secret** — add the new key to GitHub Actions secrets and reference it in the workflow `env` block:

```yaml
env:
  OTHER_API_KEY: ${{ secrets.OTHER_API_KEY }}
```

You can remove `OPENAI_API_KEY` from the workflow once you have switched over.

### What stays the same

Everything outside `generate_question()` is provider-agnostic: language selection, history logging, feedback loading, the email format, and the Railway feedback server are all unaffected by which model you use.

---

## Theme Categories

The model cycles through 7 content themes across days:

1. **Goals & disciplined execution** — long-term aims, systems, strategic assumptions
2. **Philosophy** — metaphysics, epistemology, ethics as theory, the examined life
3. **Personal reflection** — identity, memory, relationships, values in practice
4. **Historical counterfactuals** — pivotal moments, contingency, alternative histories
5. **Intellectual curiosity** — science, mathematics, language, cross-disciplinary ideas
6. **Ethics & values in practice** — moral dilemmas, competing obligations, integrity
7. **Creativity & meaning** — aesthetics, craft, narrative, meaningful work

No single category dominates any 7-day window.

---

## API Cost Estimate

Usage is extremely low — one API call per day with a small context window.
Estimated cost: **< $1/month** under normal usage.

If history grows too large, reduce `HISTORY_TAIL` (recommended range: 80–150).
