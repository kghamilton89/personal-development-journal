# Daily Journal Automation Workflow

This project automatically generates a **single daily personal development and self-actualization journaling question** and emails it to you every morning using:

- GitHub Actions (scheduler + runner)
- OpenAI API (question generation)
- Brevo (transactional email delivery)

The system:

- Maintains a historical log of all prior questions
- Feeds previous questions back to the model
- Produces a logically progressive sequence over time
- Commits new questions to the repository automatically
- Sends a formatted multilingual email (Serbian, Turkish, French, Russian, English)

---

# 1️⃣ What You Need

## Required Accounts

1. **GitHub account**
2. **OpenAI API access**
3. **Brevo account (transactional email enabled)**

---

## Required API Keys / Secrets

You will configure these as **GitHub Repository Secrets**:

### OpenAI

- `OPENAI_API_KEY`

### Brevo

- `BREVO_API_KEY`
- `BREVO_SENDER_EMAIL`
- `BREVO_SENDER_NAME`
- `BREVO_TO_EMAIL`
- `BREVO_TO_NAME`

### Optional

- `SUBJECT_PREFIX` (e.g., `Daily Prompt`)
- `HISTORY_TAIL` (number of past prompts sent to model, default 120)

---

# 2️⃣ How to Get What You Need

---

## Step 1 — Get an OpenAI API Key

1. Go to: https://platform.openai.com/
2. Log in or create an account
3. Navigate to **API Keys**
4. Click **Create new secret key**
5. Copy the key

You will store this in GitHub as:

```
OPENAI_API_KEY
```

---

## Step 2 — Set Up Brevo Transactional Email

### A) Create Brevo Account

1. Go to: https://www.brevo.com/
2. Create an account
3. Verify your email
4. Complete domain authentication if required

---

### B) Create Transactional API Key

1. Go to **Transactional → Settings → API Keys**
2. Create a new API key
3. Copy the key

Store it in GitHub as:

```
BREVO_API_KEY
```

---

### C) Add & Verify Sender

1. Go to **Senders, Domains & Dedicated IP**
2. Add and verify a sender email address
3. Use that email as:

```
BREVO_SENDER_EMAIL
```

Example:

```
journal@yourdomain.com
```

Set:

```
BREVO_SENDER_NAME
```

to whatever display name you prefer.

---

### D) Set Recipient

Use your email for:

```
BREVO_TO_EMAIL
BREVO_TO_NAME
```

---

## Step 3 — Create GitHub Repository

1. Create a new repository
2. Add the following structure:

```
.github/workflows/journal_prompt.yml
scripts/daily_prompt.py
data/journal_questions.jsonl
requirements.txt
```

3. Commit and push

---

## Step 4 — Add Repository Secrets

Go to:

```
Repository → Settings → Secrets and variables → Actions → New repository secret
```

Add all required keys listed above.

---

## Step 5 — Test the Workflow

1. Go to **Actions tab**
2. Select the workflow
3. Click **Run workflow**
4. Confirm:
   - You receive an email
   - `journal_questions.jsonl` updates
   - A new commit appears

---

# 3️⃣ Schedule Details

The GitHub Action runs at:

```
05:00 Moscow Time (MSK)
```

Because GitHub cron runs in UTC, the workflow uses:

```
0 2 * * *
```

02:00 UTC = 05:00 MSK

---

# 4️⃣ Email Format

Each email contains:

- A formatted Moscow date:  
  `13 February, 2026`

- A bullet list:

  - **Srpski**
  - **Türkçe**
  - **Français**
  - **Русский**
  - **English**

Each language contains the same philosophical question translated appropriately.

The subject line appears as:

```
Daily Prompt — 13 February, 2026
```

(If `SUBJECT_PREFIX=Daily Prompt`)

---

# 5️⃣ Overall Setup Time

| Step | Estimated Time |
|------|----------------|
| OpenAI key setup | 3–5 minutes |
| Brevo setup | 5–15 minutes |
| GitHub repo setup | 5–10 minutes |
| Testing | 5 minutes |

### Total Setup Time:
**~20–30 minutes**

---

# 6️⃣ How It Works (Architecture)

1. GitHub Action runs daily.
2. Script loads prior prompts from `journal_questions.jsonl`.
3. The most recent N prompts are sent to OpenAI.
4. The model generates the next question in sequence (5 languages).
5. The new entry is:
   - Appended to the history file
   - Emailed via Brevo API
6. GitHub commits the updated history file automatically.

---

# 7️⃣ Important Notes

## 🔒 Keep Repository Private

The entire journal history is stored in the repo.

If public, it is readable by anyone.

---

## API Costs

Usage is extremely low.  
Typical monthly cost is minimal unless you significantly increase context size.

---

## Long-Term Scaling

If history grows too large, reduce:

```
HISTORY_TAIL
```

Recommended range: 80–150.

---

# 8️⃣ Optional Enhancements

- Add sequence numbering to subject
- Add weekly philosophical themes
- Maintain a “thread summary” file for stronger continuity
- Add HTML styling improvements
- Store history externally (S3, database)
- Capture your journal responses for a closed-loop system

---

# Final Result

Every morning you receive:

A multilingual, structured, progressive philosophical journal question  
Designed to deepen discipline, identity clarity, and long-term execution.

