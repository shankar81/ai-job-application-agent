# AI Job Application Agent

An experimental LinkedIn Easy Apply assistant built with **Playwright**, **LangGraph**, and **OpenAI**.

The project scrapes LinkedIn job descriptions, compares each role against a resume-derived candidate profile, stores match data in Excel, and only starts the Easy Apply flow when the match score passes the apply threshold.

> This is a personal productivity project and is not affiliated with LinkedIn.

## What It Does

- Opens LinkedIn with a persistent Playwright browser session.
- Scrapes job cards and detailed job descriptions.
- Parses `storage/resume.pdf` into `storage/candidate_profile.json`.
- Scores each job against the candidate profile with an LLM.
- Stores scored jobs in `storage/jobs.xlsx`.
- Auto-applies only when `match_score > 5`.
- Tracks application state:
  - `not_applied`
  - `applied`
  - `skipped_low_score`
  - `failed` (also covers `aborted: <reason>` when no Telegram reply arrived)
- Handles multi-step Easy Apply forms.
- Supports text inputs, selects, checkboxes, radios, and LinkedIn typeahead comboboxes.
- Stores reusable human answers in `storage/human_answers.json`.
- Loads private local profile data from `storage/private_profile.json`.
- Sends unknown form questions to your phone via **Telegram** and waits for your reply — no need to be at the terminal. If you don't reply within the timeout, the application is marked `failed` in `jobs.xlsx` and the run continues with the next job.

## Architecture

```text
LinkedIn Jobs
    |
    v
Playwright scraper
    |
    +--> extract job card + job description
    |
    v
LangGraph agent
    |
    +--> create/update candidate profile from resume
    +--> score job fit
    +--> fill Easy Apply form fields
    |
    v
Excel tracking
    |
    +--> score, match reasons, status, timestamps
```

## Project Structure

```text
automation/
├── scraper/
│   ├── main.py          # Entry point
│   ├── session.py       # Playwright browser lifecycle
│   ├── jobs.py          # Job scraping, scoring gate, XLS status updates
│   ├── easy_apply.py    # Easy Apply modal flow
│   ├── helpers.py       # Form extraction/fill helpers
│   ├── pagination.py    # LinkedIn pagination
│   └── login.py         # Login helper
│
├── agentic/
│   ├── agent.py         # LangGraph wiring
│   ├── nodes.py         # Graph node implementations
│   ├── prompts.py       # LLM prompt builders
│   ├── memory.py        # Persistent human-answer memory
│   ├── state.py         # Agent state typing
│   ├── tools.py         # PDF, Excel, hashing, and job helpers
│   └── telegram/        # Telegram prompt layer (unknown-field questions to your phone)
│       ├── config.py    # Env loading: TELEGRAM_BOT_TOKEN, CHAT_ID, timeouts
│       ├── client.py    # Sync Telegram Bot API client (stdlib urllib + truststore)
│       ├── formatter.py # Message templates
│       └── prompt.py    # ask_user() — send + long-poll for reply
│
├── scripts/
│   └── smoke_test_telegram.py  # Standalone send/reply test (run from your Mac)
│
├── storage/
│   ├── resume.pdf               # Local, ignored
│   ├── candidate_profile.json   # Generated, ignored
│   ├── private_profile.json     # Local private facts, ignored
│   ├── human_answers.json       # Generated answer memory, ignored
│   └── jobs.xlsx                # Generated tracking workbook, ignored
│
├── pyproject.toml
└── uv.lock
```

## Setup

Use Python 3.12+.

```bash
uv sync
```

Create a local `.env` file:

```bash
OPENAI_API_KEY=your_api_key
EMAIL=your_linkedin_email
PASSWORD=your_linkedin_password

# Telegram (optional but recommended — without these, any unknown form
# field will fail the application instead of asking you for an answer)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_numeric_chat_id_from_userinfobot
TELEGRAM_REPLY_TIMEOUT=300   # seconds to wait per attempt (default 5 min)
TELEGRAM_MAX_ATTEMPTS=2      # initial send + N-1 reminders (default 2)
```

Add your resume:

```text
storage/resume.pdf
```

Optionally add private local facts for form filling:

```text
storage/private_profile.json
```

Example shape:

```json
{
  "location_details": {
    "city": "Mumbai",
    "state": "Maharashtra",
    "country": "India"
  },
  "salary_details": {
    "current_ctc": "example",
    "expected_ctc": "example"
  },
  "application_preferences": {
    "notice_period_days": 90,
    "how_did_you_hear_about_us": "LinkedIn"
  }
}
```

Run:

```bash
python scraper/main.py
```

The browser uses a persistent profile in `userdata/`, so LinkedIn sessions can survive across runs.

## Telegram Setup (Optional)

When the agent hits a form field it can't answer from your resume, profile, or memory, it pushes the question to your Telegram chat and waits for your reply. This lets the bot run unattended on your laptop while you respond from your phone.

**One-time setup:**

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow prompts. Copy the token it gives you.
2. Open a chat with your new bot and send `/start` (Telegram requires you to initiate contact before the bot can message you).
3. Message [@userinfobot](https://t.me/userinfobot), copy the numeric `Id` it replies with.
4. Put both into `.env` as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

**Verify it works:**

```bash
.venv/bin/python scripts/smoke_test_telegram.py           # send-only test
.venv/bin/python scripts/smoke_test_telegram.py --reply   # send + wait for reply
```

For the `--reply` test, **long-press the message on your phone and choose "Reply"** before typing your answer. The bot matches replies by their `reply_to_message_id`, so a free-form message won't satisfy it (this avoids confusion when multiple questions queue up).

**Behavior on no reply:** the bot waits `TELEGRAM_REPLY_TIMEOUT` seconds, sends a reminder, waits the same amount again, then marks the application `failed` in `jobs.xlsx` and moves on. The full run is never blocked by a single missing answer.

**Corporate VPN / antivirus note:** the client uses [`truststore`](https://pypi.org/project/truststore/) so HTTPS calls to `api.telegram.org` work even when a Zscaler/Cisco-style TLS interceptor is in your network path.

## Data Outputs

`storage/jobs.xlsx` stores:

- job title, company, location, URL
- match score
- strong matches
- missing/weaker areas
- job summary and required skills
- application status
- applied timestamp
- error text for failed attempts

`storage/human_answers.json` stores answers provided during form filling so repeated questions can be reused later.

`storage/private_profile.json` stores private local facts such as address, salary, notice period, work authorization, and application preferences. It is loaded into the form-fill prompt at runtime and intentionally ignored by git.

## Safety Notes

- Keep `.env`, `userdata/`, `auth.json`, `storage/`, `PROJECT_CONTEXT.md`, and screenshots private.
- Review applications periodically in LinkedIn to ensure submissions match your intent.
- Do not expose resume, phone, salary, auth state, browser profile, or prompt logs in a public repo.
- Use match-score gating and company review to avoid low-quality or irrelevant applications.

## Current Roadmap

- Add company research with a search MCP such as Tavily.
- Add `company_fit_score` and `overall_score`.
- Improve canonical keys for persistent human-answer memory.
- Add unit tests for Excel updates, job dedupe, and form filling.
- Make search query, threshold, and max jobs configurable.
