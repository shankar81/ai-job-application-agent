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
  - `failed`
- Handles multi-step Easy Apply forms.
- Supports text inputs, selects, checkboxes, radios, and LinkedIn typeahead comboboxes.
- Stores reusable human answers in `storage/human_answers.json`.

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
│   └── tools.py         # PDF, Excel, hashing, and job helpers
│
├── storage/
│   ├── resume.pdf
│   ├── candidate_profile.json
│   ├── human_answers.json
│   └── jobs.xlsx
│
├── PROJECT_CONTEXT.md
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
```

Add your resume:

```text
storage/resume.pdf
```

Run:

```bash
python scraper/main.py
```

The browser uses a persistent profile in `userdata/`, so LinkedIn sessions can survive across runs.

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

## Safety Notes

- Keep `.env`, `userdata/`, `auth.json`, `storage/`, and screenshots private.
- Review applications periodically in LinkedIn to ensure submissions match your intent.
- Do not expose resume, phone, salary, auth state, browser profile, or prompt logs in a public repo.
- Use match-score gating and company review to avoid low-quality or irrelevant applications.

## Current Roadmap

- Add company research with a search MCP such as Tavily.
- Add `company_fit_score` and `overall_score`.
- Improve canonical keys for persistent human-answer memory.
- Add unit tests for Excel updates, job dedupe, and form filling.
- Make search query, threshold, and max jobs configurable.
