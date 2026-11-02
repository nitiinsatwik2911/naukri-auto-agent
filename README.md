# Naukri-Autoapply-Bot

> Automation that applies to jobs on Naukri.com automatically for faster job hunting. Uses **Selenium** for browser automation and **BeautifulSoup** for parsing job listings.

## 📋 Features

- ✅ Automatically logs in to Naukri.com
- ✅ **Multi-tab parallel search** — Opens each keyword category in its own browser tab simultaneously
- ✅ Searches for jobs by keywords and location (updated for 2026 Naukri redesign)
- ✅ Visits job listings and clicks "Apply" / "Apply on company site"
- ✅ Handles custom first/last name fields and "Submit and Apply" flow
- ✅ Detects daily application quota limits
- ✅ Saves results (passed/failed) to a CSV file
- ✅ Uses **Microsoft Edge** browser
- ✅ Uses `webdriver-manager` for automatic driver download (no manual setup!)

## 🚀 How Multi-Tab Parallel Search Works

Instead of processing each keyword one-by-one (slow), the bot **opens every keyword search page in its own browser tab simultaneously**:

```
Keyword: "python developer"  → Tab 1 (Page 1) + Tab 2 (Page 2)
Keyword: "data analyst"     → Tab 3 (Page 1) + Tab 4 (Page 2)
Keyword: "software engineer" → Tab 5 (Page 1) + Tab 6 (Page 2)
...all open at the same time!
```

**Benefits:**
- ⚡ **Much faster** — all keyword searches load in parallel instead of waiting sequentially
- 📊 **More jobs found** — each keyword gets equal attention
- 🔄 **Smart deduplication** — duplicate job links across keywords are automatically removed before applying

## 🚀 Quick Start

### Prerequisites
- **Python 3.7+** installed on your system
- **Microsoft Edge** browser installed
- A valid **Naukri.com** account

### 1. Clone the repository

```bash
git clone https://github.com/lordzohar/Naukri-autoapply-bot.git
cd Naukri-autoapply-bot
```

### 2. Install dependencies

It's recommended to use a virtual environment:

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv

# Activate it:
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configure your credentials

```bash
# Copy the example environment file
copy .env.example .env
```

Then edit **`.env`** (⚠️ NEVER commit this file) with your details:

```ini
# Your Naukri.com login credentials
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password

# Your personal details
FIRSTNAME=YourFirstName
LASTNAME=YourLastName

# Job search keywords (comma-separated)
KEYWORDS=python developer, data analyst, software engineer

# Location (leave empty for all locations, or specify a city like "bangalore", "mumbai", "remote")
LOCATION=bangalore

# Number of search result pages to scrape per keyword (default: 2)
PAGES_PER_KEYWORD=2

# Maximum applications per run (Naukri allows ~100/day)
MAX_APPLICATIONS=50
```

### 4. Run the bot

```bash
python cli.py search
```

> **Note:** The script uses `webdriver-manager` to automatically download the correct EdgeDriver. No manual driver setup needed!

### 5. Check results

After running, results are saved to **`naukriapplied.csv`** with two columns:
- `passed` — URLs of jobs successfully applied to
- `failed` — URLs where the apply attempt failed

## 🔧 2026 Naukri.com Update

The bot has been updated to work with Naukri.com's 2026 redesign. Key changes:

| Old (original script) | New (updated) |
|----------------------|---------------|
| Job cards: `article.jobTuple.bgWhite.br4.mb-8` | Job cards: `div.srp-jobtuple-wrapper > div.cust-job-tuple` |
| Title links: `a.title.fw500.ellipsis` | Title links: `a.title` (inside `h2`) |
| Search URL: `/{keyword}-{page}` | Search URL: `/{keyword}-jobs` or `/{keyword}-jobs-in-{location}` |
| Apply button: `//*[text()='Apply']` | Apply button: `//button[contains(text(),'Apply on company site')]` |
| Page structure: `article` tags | Page structure: React/Next.js app using `div` with hashed CSS classes |

## 📁 Project Structure

```
naukri-auto-agent/
├── cli.py                     # python cli.py search | filter | recommended
├── requirements.txt
├── pytest.ini
├── .env.example               # All settings, with example values (copy to .env)
├── SYSTEM_DESIGN.md           # Architecture
├── config/
│   ├── resume.example.txt     # Copy to config/resume.txt (gitignored)
│   └── resume.txt             # Resume facts used by the LLM fallback
├── src/naukri_agent/
│   ├── config.py              # Only place that reads .env (+ profile, skill years)
│   ├── browser.py             # Edge driver setup + Naukri login
│   ├── search.py              # Keyword + filter modes: tabs, link collection, run()
│   ├── filters.py             # FILTER_URL cleanup + search-API helpers (pure, tested)
│   ├── jobapi.py              # Filter mode: replays the page's search API call after login
│   ├── recommended.py         # Recommended-feed mode
│   ├── apply.py               # quick_apply + per-run apply loop
│   ├── chatbot.py             # Screening-question DOM handling (Selenium)
│   ├── results.py             # naukriapplied.csv + job_history.csv (skip settled jobs)
│   └── answers/               # No browser needed (unit-tested)
│       ├── store.py           # application_answers.csv
│       ├── rules.py           # Profile-based rules
│       ├── llm.py             # claude CLI fallback
│       ├── options.py         # Match answers to radio/select options
│       └── resolver.py        # saved -> rule -> llm
├── tests/                     # test_rules, test_options, test_resolver
├── data/                      # Generated files (gitignored, folder set by DATA_DIR)
│   ├── application_answers.csv
│   ├── naukriapplied.csv
│   ├── job_history.csv
│   └── debug_pages/
├── drivers/                   # Optional local msedgedriver (gitignored)
└── Naukri autoapply jobs.ipynb  # Legacy notebook
```

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Browser driver not found | `webdriver-manager` handles this automatically. Ensure you're connected to the internet on first run. |
| Login failed | Double-check your `NAUKRI_EMAIL` and `NAUKRI_PASSWORD` in `.env` |
| No jobs found | Try broader keywords or remove the location filter |
| "Daily quota expired" | Naukri limits daily applications. Try again the next day. |
| Script too fast/slow | Adjust the `time.sleep()` values in the script if needed |
| "Apply on company site" opens external site | This is expected — many Naukri jobs now redirect to company career pages |

## ⚠️ Disclaimer

- Use this bot responsibly and in accordance with Naukri.com's Terms of Service
- The bot mimics human behavior but excessive automation may lead to account restrictions
- This project is for educational purposes

## 🔗 Original Repository

[github.com/lordzohar/Naukri-autoapply-bot](https://github.com/lordzohar/Naukri-autoapply-bot)