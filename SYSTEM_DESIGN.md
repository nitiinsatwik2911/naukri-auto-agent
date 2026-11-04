# Naukri Auto-Apply Agent: System Design

## 1. Purpose

Automate job applications on Naukri.com. The agent logs in, finds jobs by keyword/location or from the "Recommended" feed, applies, and answers recruiter screening questions on the user's behalf. It records what was applied to and what answers were given.

**Non-goals:** multi-user support, a hosted service, bypassing Naukri's daily quota.

## 2. High-Level Architecture

```
                        ┌────────────────────────────┐
                        │  Config layer              │
                        │  .env  (creds, keywords,   │
                        │  CTC, notice period, ...)  │
                        │  resume.txt                │
                        └─────────────┬──────────────┘
                                      │
        ┌─────────────────────────────┼──────────────────────────────┐
        │                             │                              │
┌───────▼─────────┐         ┌─────────▼─────────┐                    │
│ Naukri-Edge.py  │         │Naukri-Recommended │   Entry points     │
│ (keyword search)│         │ .py (feed + chat  │   (two modes)      │
│                 │         │  drawer handler)  │                    │
└───────┬─────────┘         └─────────┬─────────┘                    │
        │ quick_apply(driver, link)   │ own chatbot handlers         │
        │                             │ (radio / contenteditable)    │
        ▼                             ▼                              │
┌─────────────────────────────────────────────────┐                  │
│ answer_bot.py  (screening-question engine)      │◄─────────────────┘
│                                                 │
│  find_answer(question)                          │
│    1. saved   → application_answers.csv        │
│    2. rule    → PROFILE + SKILL_YEARS           │
│    3. llm     → `claude -p` CLI + resume.txt    │
│  match_option()  → radio / select / checkbox    │
│  _fill_field()   → Selenium DOM interaction     │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│ Selenium + Edge (drivers/msedgedriver.exe)      │
│ BeautifulSoup/lxml for parsing job listings     │
└───────────────┬─────────────────────────────────┘
                ▼
          naukri.com (React/Next.js SPA)

Outputs:  naukriapplied.csv (passed/failed URLs)
          application_answers.csv (learned Q&A, user-editable)
          debug_pages/ (HTML dumps on failure)
```

## 3. Components

| Component | File | Responsibility |
|---|---|---|
| Keyword bot | [Naukri-Edge.py](Naukri-Edge.py) | Validate config, create Edge driver, log in, build search URLs, open one tab per keyword/page, scrape job links, dedupe, apply up to `MAX_APPLICATIONS`, save results |
| Recommended bot | [Naukri-Recommended.py](Naukri-Recommended.py) | Pick recommendation tabs, select jobs, apply, drive the chatbot drawer (radio buttons, contenteditable input, Save button) with fuzzy-matched saved answers |
| Answer engine | [answer_bot.py](answer_bot.py) | `quick_apply()`: click Quick Apply, detect chatbot, extract questions, resolve answers, fill and submit |
| Browser | [browser.py](browser.py) | Shared Edge driver creation (local driver path, webdriver-manager, or Selenium Manager) and Naukri login |
| Config | [.env](.env), [.env.example](.env.example) | Credentials, search params, personal answers (CTC, notice period, relocation) |
| Knowledge | [resume.txt](resume.txt), [application_answers.csv](application_answers.csv) | Facts for the LLM prompt; persisted, human-editable Q&A memory |
| Legacy | [Naukri autoapply jobs.ipynb](Naukri%20autoapply%20jobs.ipynb) | Original notebook version (unused) |

## 4. Core Flows

### 4.1 Keyword search flow (Naukri-Edge)
1. `validate_config()` → fail fast on missing credentials/keywords.
2. `create_edge_driver()` → login via `login_naukri()`.
3. `build_search_urls()` → `/{keyword}-jobs[-in-{location}]` × `PAGES_PER_KEYWORD`.
4. `open_tabs_parallel()` → one browser tab per URL (parallel page loads; Selenium itself is still single-threaded).
5. `collect_job_links_from_tab()` per window handle → BeautifulSoup parses `div.srp-jobtuple-wrapper a.title`.
6. Dedupe links, then `apply_to_jobs()` loops through `quick_apply()`.
7. Stop on quota-exceeded message or `MAX_APPLICATIONS`; `save_results()` writes `naukriapplied.csv`.

### 4.2 Screening-question flow (answer_bot)
```
quick_apply(link)
  └─ open job → click "Quick apply"
       ├─ no chatbot → applied
       └─ chatbot opens
            loop until done / timeout (60s):
              read latest bot question + field type (text/number/radio/select/checkbox/textarea)
              find_answer():  saved  →  rule  →  llm   (first non-empty wins)
              match_option() for choice fields (numeric range matching, fuzzy text)
              _fill_field() → submit message / click Save
              save_answer() (source = saved|rule|llm) for later review
            on failure → _dump_debug() writes HTML to debug_pages/
```

**Answer priority** (user control increases downward in the chain):
1. `application_answers.csv`: exact normalised match, or difflib ratio ≥ 0.95. Hand-edited rows always win.
2. Rules: regex/keyword rules over `PROFILE` plus `SKILL_YEARS` (longest skill key wins).
3. LLM: `claude -p --model haiku` subprocess, run from a temp dir, prompt built from `resume.txt` + profile, 90s timeout. Returns `""` on failure so the question is skipped rather than guessed.

## 5. Data Model

| Store | Format | Schema | Lifecycle |
|---|---|---|---|
| `application_answers.csv` | CSV (utf-8) | `question_text, answer, field_type, created_at, source, options` | Append-only by bot; user may edit; gitignored |
| `naukriapplied.csv` | CSV | `passed, failed` (URL columns) | Overwritten/appended per run; gitignored |
| `.env` | dotenv | see `.env.example` | Manual; never committed |
| `debug_pages/` | HTML | page snapshot per failure | Ephemeral; gitignored |

## 6. External Dependencies

| Dependency | Use | Risk |
|---|---|---|
| Naukri.com DOM | Selectors (`srp-jobtuple-wrapper`, chat drawer, hashed classes) | **Highest.** Frontend redesigns break selectors with no notice |
| Microsoft Edge + msedgedriver | Browser automation | Driver/browser version mismatch (`drivers/` pins a binary) |
| `claude` CLI | LLM answers | Needs CLI installed and authenticated; adds latency; non-deterministic |
| selenium, bs4, lxml, pandas, python-dotenv, webdriver-manager | See [requirements.txt](requirements.txt) | Low |

## 7. Cross-Cutting Concerns

- **Rate/quota:** Naukri allows ~100 applications/day; bot caps per run with `MAX_APPLICATIONS` and detects the quota message.
- **Bot detection / ToS:** use human-like sleeps, a persistent logged-in session, and modest volume. Excessive automation risks account restriction.
- **Reliability:** explicit waits (`WebDriverWait`), stale-element retries, per-job try/except so one failure doesn't abort the run, debug HTML dumps.
- **Idempotency:** dedupe links within a run. Applied URLs aren't yet checked across runs (see recommendations).
- **Observability:** Python `logging` to console. No persistent run log.
- **Security:** credentials in `.env` only; LLM subprocess runs in a temp cwd so no project context leaks.

## 8. Issues Found in the Current Structure

1. **Personal data is hardcoded** in [answer_bot.py:63-87](answer_bot.py#L63-L87) (name, email, phone, LinkedIn, employer, college). It belongs in `.env` or a profile file, and it is committed to git.
2. **`.gitignore` bug:** the last two entries are merged into one line, `application_answers.csvdrivers/`. Neither `application_answers.csv` nor `drivers/` is actually ignored.
3. **`naukri_venv/` is not ignored** (only `venv/`, `env/`, `.venv/` are). It shows up as untracked with ~8,800 files.
4. **Duplicated logic:** `Naukri-Recommended.py` has its own `load_answers`, `fuzzy_lookup`, `save_answer`, `create_edge_driver` and `login_naukri`, duplicating `answer_bot.py` and `Naukri-Edge.py`.
5. **Hyphenated script names** (`Naukri-Edge.py`) can't be imported as modules.
6. **README is out of date.** It says `webdriver-manager` auto-downloads the driver, but a local `drivers/msedgedriver.exe` exists. It also omits `answer_bot.py` and the Recommended bot.
7. **Learned answers are never expired:** a wrong LLM answer is reused forever until manually edited.

## 9. Project Structure (implemented)

```
naukri-auto-agent/
├── README.md
├── SYSTEM_DESIGN.md
├── requirements.txt
├── .env.example
├── .gitignore                 # fixed: one entry per line, add naukri_venv/
├── config/
│   ├── resume.example.txt     # example; copy to resume.txt (gitignored)
│   └── resume.txt
├── src/naukri_agent/
│   ├── __init__.py
│   ├── config.py              # only reader of .env; profile + SKILL_YEARS (no profile.yaml: everything lives in .env)
│   ├── browser.py             # create_edge_driver, login, waits, tab helpers
│   ├── search.py              # build_search_urls, collect_job_links (keyword mode)
│   ├── recommended.py         # recommended-feed mode
│   ├── apply.py               # quick_apply orchestration, quota detection
│   ├── answers/
│   │   ├── store.py           # CSV read/write, normalisation
│   │   ├── rules.py           # profile rules
│   │   ├── llm.py             # claude CLI wrapper
│   │   ├── resolver.py        # find_answer: saved → rule → llm
│   │   └── options.py         # match_option, range matching
│   ├── chatbot.py             # DOM handlers: radio, select, contenteditable, save
│   └── results.py             # applied/failed log + job_history.csv (cross-run dedupe)
├── cli.py                     # `python cli.py search|recommended`
├── data/                      # gitignored runtime output
│   ├── application_answers.csv
│   ├── naukriapplied.csv
│   ├── job_history.csv
│   └── debug_pages/
├── drivers/                   # gitignored (or rely on Selenium Manager)
└── tests/
    ├── test_rules.py
    ├── test_options.py        # pure functions, no browser needed
    └── test_resolver.py
```

**Why this split:** everything that doesn't need a browser (rules, option matching, resolver, store) becomes unit-testable. Only `browser.py`, `chatbot.py` and `search.py` touch Selenium, so a Naukri DOM change is confined to those files.

## 10. Status of Recommended Steps

Done: `.gitignore` fixed; profile, skill years and every tunable moved to `.env` (read only by `config.py`); shared browser/login module; cross-run dedupe; `data/` folder; package split; unit tests for rules, options and resolver; README refreshed.
Also done: recommended mode rewritten on Naukri's API with a tab menu, so every mode now shares `pipeline.py`, `apply.py`, `chatbot.py` and `answers/`; early-access `interested` mode; pluggable LLM providers.
Open: purge secrets from git history; expire stale LLM answers.
