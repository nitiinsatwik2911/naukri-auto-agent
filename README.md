# Naukri Auto-Apply Agent

Applies to jobs on Naukri.com for you. It finds jobs, applies, and answers the recruiter's screening questions from your profile, your saved answers, and (optionally) an LLM. Built with **Selenium** (Microsoft Edge) and **BeautifulSoup**. See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the architecture.

## Features

- **Four modes**: keyword search, your own filtered search URL, Naukri's recommended jobs (you pick the tabs), and early-access "I'm interested"
- **Pro and free accounts**: handles both the "Quick apply" button (Pro) and the plain "Apply" button (free)
- **Screening questions answered automatically**: saved answers, then profile rules, then an LLM (see below)
- **Learns**: every answer used is saved to a CSV you can edit; your edits always win
- **Skips settled jobs**: jobs already applied to, already applied, or external-site are remembered and not re-opened on later runs
- **Daily quota detection**, external-site jobs skipped, results saved to CSV
- **All settings in `.env`**, nothing hardcoded in the Python files

## The four modes

| Command | What it does |
|---|---|
| `python cli.py search` | Opens one browser tab per keyword and page (`KEYWORDS`, `LOCATION`, `PAGES_PER_KEYWORD`), collects job links, de-duplicates, then applies |
| `python cli.py filter` | You paste a Naukri search URL with your filters applied into `FILTER_URL`. The bot logs in and reads every result page from Naukri's search API, so it applies to the same jobs your logged-in browser shows |
| `python cli.py recommended` | Reads your recommendations from Naukri's API and shows the tabs (All, Top companies, Strong match, Actively reviewing, Salary growth) with how many jobs you can apply to in each. You pick one or more, for example `3` or `3,5`, or skip the question with `--tabs 3,5`. Jobs that apply on the company's site, jobs already applied to, and settled jobs are left out. It then applies with the same loop and answer engine as the other modes |
| `python cli.py interested` | Opens each early-access "View opportunity" card and clicks "I'm interested" (`INTERESTED_MAX` cards). This shares your interest with the recruiter and is not an application |

## How screening questions are answered

For each question the bot tries these in order and uses the first answer found:

1. **Saved answers**: `data/application_answers.csv` (exact match, or at least `SAVED_ANSWER_CUTOFF` similar). Anything you edit there always wins.
2. **Profile rules**: your `.env` profile (name, email, phone, CTC, notice period, ...) and `SKILL_YEARS` for "years of experience in X".
3. **LLM fallback**: an AI command-line tool, using `config/resume.txt` and your profile. Set `LLM_PROVIDER` in `.env` to `claude`, `copilot`, or both (`claude,copilot`, tried in that order). The tool must be installed and logged in; if it is missing, not logged in, or `LLM_PROVIDER` is empty, the bot skips it and saves the question as `unanswered` with an empty answer. Fill in the answer in the CSV and it is used on the next run.

   Each provider's command is a line in `.env` (`LLM_CLAUDE_COMMAND`, `LLM_COPILOT_COMMAND`), so you can change flags or add another tool (`LLM_<NAME>_COMMAND`) without touching the code. A command containing `{prompt}` receives the question as an argument; otherwise it is sent on stdin. Check the flags with `claude --help` / `copilot --help`.

Radio buttons, dropdowns and checkboxes are matched to the options by exact text, yes/no, number ranges (for example "3-5 years"), then fuzzy match (`OPTION_MATCH_CUTOFF`).

## Quick start

### Prerequisites
- **Python 3.8+**
- **Microsoft Edge**
- A **Naukri.com** account (Pro or free)
- Optional, for the LLM fallback: the **`claude` CLI** or the **GitHub Copilot CLI** (`copilot`), installed and logged in

### 1. Install

```bash
git clone https://github.com/nitiinsatwik2911/naukri-auto-agent.git
cd naukri-auto-agent

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### 2. Configure

```bash
copy .env.example .env
copy config\resume.example.txt config\resume.txt
```

Edit **`.env`** (never commit it) and `config/resume.txt`. `.env.example` documents every setting, grouped by purpose:

1. Naukri account
2. Run modes (keyword search, filter URL, recommended tabs, early access)
3. Files and folders (`DATA_DIR`, `RESUME_FILE`)
4. Browser (`EDGE_DRIVER_PATH`)
5. Your profile and `SKILL_YEARS`
6. Answer-matching cut-offs
7. LLM fallback (`LLM_PROVIDER`, per-provider commands)

Numeric settings are required: if one is missing the bot stops and names it.

### 3. Run

```bash
python cli.py search
python cli.py filter
python cli.py recommended            # asks which tabs
python cli.py recommended --tabs 3,5
python cli.py interested
```

If `EDGE_DRIVER_PATH` is empty, `webdriver-manager` downloads the driver; if that fails, Selenium Manager or your PATH is used.

### 4. Check results

Everything the bot writes goes to the `data/` folder (set by `DATA_DIR`):

| File | Contents |
|---|---|
| `application_answers.csv` | Every screening answer used and its source (`saved`, `rule`, `llm`, `unanswered`). Edit it to correct answers. |
| `naukriapplied.csv` | `passed` and `failed` job links of the **last run** (overwritten each run) |
| `job_history.csv` | Outcome of every job ever visited (`applied`, `already`, `external`, `failed`, `unanswered`). The first three are skipped on later runs. |
| `debug_pages/` | HTML and screenshots saved when the bot gets stuck |

## Project structure

```
naukri-auto-agent/
├── cli.py                     # python cli.py search | filter | recommended
├── requirements.txt
├── pytest.ini
├── .env.example               # Every setting, with example values (copy to .env)
├── SYSTEM_DESIGN.md           # Architecture
├── config/
│   ├── resume.example.txt     # Copy to config/resume.txt (gitignored)
│   └── resume.txt             # Resume facts used by the LLM fallback
├── src/naukri_agent/
│   ├── config.py              # Only place that reads .env (+ profile, skill years)
│   ├── browser.py             # Edge driver setup + Naukri login
│   ├── search.py              # Keyword + filter modes: link collection
│   ├── filters.py             # FILTER_URL cleanup + search-API helpers (pure, tested)
│   ├── jobapi.py              # Filter mode: replays the page's search API call after login
│   ├── recommended.py         # Recommended mode: tab menu + API (pure helpers tested)
│   ├── interested.py          # Early-access "I'm interested" mode
│   ├── netapi.py              # Capture + replay a logged-in page's API call (GET or POST)
│   ├── pipeline.py            # Shared run loop: collect, skip settled, apply, summary
│   ├── apply.py               # Quick apply / Apply flow + per-run apply loop
│   ├── chatbot.py             # Screening-question DOM handling (Selenium)
│   ├── results.py             # naukriapplied.csv + job_history.csv
│   └── answers/               # No browser needed (unit-tested)
│       ├── store.py           # application_answers.csv
│       ├── rules.py           # Profile-based rules
│       ├── llm.py             # LLM fallback: claude / copilot CLI, set in .env
│       ├── options.py         # Match answers to radio/select options
│       └── resolver.py        # saved -> rule -> llm
├── tests/                     # test_rules, test_options, test_resolver, test_filters, test_llm, test_recommended
├── data/                      # Generated files (gitignored)
├── drivers/                   # Optional local msedgedriver (gitignored)
└── Naukri autoapply jobs.ipynb  # Legacy notebook
```

## Tests

```bash
pip install pytest
pytest
```

The tests need no browser or network and set their own environment.

## Troubleshooting

| Issue | Solution |
|---|---|
| `X is not set in .env` | Add the named setting; `.env.example` lists them all |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` in your virtual environment |
| Browser driver problems | Set `EDGE_DRIVER_PATH`, or leave it empty so `webdriver-manager` downloads one |
| Login failed | Check `NAUKRI_EMAIL` and `NAUKRI_PASSWORD` |
| Most jobs "Skipped: external company-site" | Normal: many Naukri jobs apply on the company's own site, which the bot skips |
| Many jobs "could not complete application" | Check `data/debug_pages/` for the page the bot got stuck on |
| `LLM 'x': 'x' is not installed or not on PATH` | Install that CLI, or change `LLM_PROVIDER` / `LLM_<NAME>_COMMAND` in `.env` |
| Questions logged as `unanswered` | Fill in the `answer` column in `data/application_answers.csv`; it is used next run. Or set `LLM_PROVIDER` and log in to that CLI (`claude` or `copilot`) |
| `Recommended` tab shows "listed without details, not usable" | Naukri lists those jobs in the tab but sends details for only some; the bot can only use the ones it has details for |
| `python cli.py filter` opens the wrong page | `FILTER_URL` in `.env` must be a search URL (like `https://www.naukri.com/ai-engineer-jobs?...`), not the recommended page |
| Filter mode finds few jobs | Your filters match few jobs. Loosen them (for example remove `jobAge`) in `FILTER_URL` |
| `Search API call ... not seen on the page` | Naukri changed its API. Update `FILTER_API_PATH` / `FILTER_API_HEADERS` in `.env` |
| `Daily quota expired` | Naukri limits daily applications; try again tomorrow |
| Lines like `fallback_task_provider.cc ... ERROR` | Harmless Edge/Chromium warnings; ignore them |

## Disclaimer

- Use this bot in line with Naukri.com's Terms of Service
- Heavy automation can lead to account restrictions, so keep `MAX_APPLICATIONS` modest
- Your `.env`, resume and `data/` hold personal information and are gitignored; do not commit them
- This project is for educational purposes
