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
