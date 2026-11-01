"""
Quick-apply question answering for the Naukri bot.

Flow: click "Quick apply" -> if Naukri opens the screening-question chatbot,
answer each question and submit. Answer priority:
  1. application_answers.csv  (anything you typed/edited there always wins)
  2. resume-based PROFILE rules below
  3. an LLM (the `claude` CLI) prompted with resume.txt
Every answer used is saved to application_answers.csv (source = rule / llm) so
you can review and edit it; edited answers are reused on later runs.
"""
import csv
import difflib
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime

from dotenv import load_dotenv
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

load_dotenv()  # PROFILE is built at import time, so .env must be loaded first

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANSWERS_CSV = os.path.join(BASE_DIR, "application_answers.csv")
RESUME_TXT = os.path.join(BASE_DIR, "resume.txt")
DEBUG_DIR = os.path.join(BASE_DIR, "debug_pages")
CSV_FIELDS = ["question_text", "answer", "field_type", "created_at", "source", "options"]
LLM_MODEL = os.getenv("LLM_MODEL", "haiku")
LLM_TIMEOUT = 90

# ---------------------------------------------------------------------------
# Profile (from resume + .env)
# ---------------------------------------------------------------------------
def _env(name, default=""):
    return os.getenv(name, default).strip()


# Years per skill, derived from resume dates (Python/automation since May 2022,
# AI/GenAI since Sep 2024, AWS at Uptycs May 2022-Feb 2024, Robot at Komprise).
SKILL_YEARS = {
    "python": "4", "selenium": "4", "automation": "4", "test automation": "4",
    "sql": "4", "git": "4", "linux": "4", "rest api": "4", "api testing": "4",
    "pytest": "4", "jenkins": "2", "ci/cd": "2", "docker": "2", "gitlab": "2",
    "mongodb": "4", "bash": "4", "c++": "2", "fastapi": "2",
    "aws": "2", "boto3": "2", "cloudwatch": "2",
    "robot framework": "1", "sdet": "1",
    "generative ai": "2", "genai": "2", "gen ai": "2", "llm": "2", "rag": "2",
    "agentic": "2", "mcp": "2", "prompt engineering": "2", "langchain": "2",
    "nlp": "2", "hugging face": "2", "huggingface": "2", "transformers": "2",
    "pytorch": "2", "tensorflow": "2", "keras": "2", "scikit": "2",
    "machine learning": "2", "deep learning": "2", "ai": "2", "ml": "2",
    "fine-tuning": "1", "fine tuning": "1", "qlora": "1", "peft": "1",
    "5g": "2", "telecom": "2",
}


def build_profile():
    return {
        "full_name": _env("FULL_NAME"),
        "first_name": _env("FIRSTNAME"),
        "last_name": _env("LASTNAME"),
        "email": _env("PROFILE_EMAIL"),
        "phone": _env("PROFILE_PHONE"),
        "city": _env("PROFILE_CITY"),
        "linkedin": _env("PROFILE_LINKEDIN"),
        "total_experience": _env("TOTAL_EXPERIENCE", "4"),
        "current_company": _env("PROFILE_COMPANY"),
        "designation": _env("PROFILE_DESIGNATION"),
        "degree": _env("PROFILE_DEGREE"),
        "branch": _env("PROFILE_BRANCH"),
        "college": _env("PROFILE_COLLEGE"),
        "cgpa": _env("PROFILE_CGPA"),
        # Not on resume -> must come from .env, otherwise unanswered
        "current_ctc": _env("CURRENT_CTC"),
        "expected_ctc": _env("EXPECTED_CTC"),
        "notice_period": _env("NOTICE_PERIOD"),           # e.g. "30 days"
        "immediate_joiner": _env("IMMEDIATE_JOINER"),     # yes / no
        "relocate": _env("WILLING_TO_RELOCATE"),          # yes / no
        "work_from_office": _env("WILLING_TO_WORK_FROM_OFFICE"),
        "work_authorized": _env("AUTHORIZED_TO_WORK_IN_INDIA"),
    }


PROFILE = build_profile()


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#/. -]", " ", (text or "").lower())).strip()


def rule_answer(question):
    """Return an answer string from the profile rules, or '' when unknown."""
    q = norm(question)
    p = PROFILE

    def has(*words):
        return any(w in q for w in words)

    if has("first name"):
        return p["first_name"]
    if has("last name", "surname"):
        return p["last_name"]
    if has("full name", "your name") or q in ("name", "name *"):
        return p["full_name"]
    if has("email"):
        return p["email"]
    if has("phone", "mobile", "contact number", "whatsapp"):
        return p["phone"]
    if has("linkedin"):
        return p["linkedin"]
    if has("expected ctc", "expected salary", "expected compensation", "expected package"):
        return p["expected_ctc"]
    if has("current ctc", "current salary", "current compensation", "current package", "present ctc", "fixed ctc"):
        return p["current_ctc"]
    if has("immediate joiner", "join immediately", "immediately available"):
        return p["immediate_joiner"]
    if has("notice period", "how soon", "when can you join", "joining time"):
        return p["notice_period"]
    if has("relocat"):
        return p["relocate"]
    if has("work from office", "wfo", "onsite", "on site", "hybrid"):
        return p["work_from_office"]
    if has("authorized to work", "authorised to work", "work permit", "eligible to work"):
        return p["work_authorized"]
    if has("current company", "current employer", "present company", "current organization", "current organisation"):
        return p["current_company"]
    if has("current designation", "current role", "job title", "designation"):
        return p["designation"]
    if has("highest qualification", "highest education", "degree", "qualification"):
        return p["degree"]
    if has("college", "university", "institute"):
        return p["college"]
    if has("cgpa", "percentage", "gpa"):
        return p["cgpa"]
    if has("current location", "current city", "which city", "where are you", "city are you")             and not has("interview", "available", "willing", "relocate"):
        return p["city"]

    if has("experience", "years", "yrs"):
        # Skill-specific experience: longest matching skill key wins
        skills = [s for s in SKILL_YEARS if re.search(r"(^| )" + re.escape(s) + r"( |$)", q)]
        if skills:
            return SKILL_YEARS[max(skills, key=len)]
        if has("total", "overall", "relevant", "work experience", "professional experience"):
            return p["total_experience"]
    return ""


# ---------------------------------------------------------------------------
# Learned answers (application_answers.csv)
# ---------------------------------------------------------------------------
def _read_rows():
    if not os.path.exists(ANSWERS_CSV):
        return []
    with open(ANSWERS_CSV, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_rows(rows):
    with open(ANSWERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_saved_answers():
    answers = {}
    for row in _read_rows():
        q, a = norm(row.get("question_text")), (row.get("answer") or "").strip()
        if q and a:
            answers[q] = a
    return answers


def save_answer(question, answer, field_type, source, options=None):
    """Record the answer used for a question (no-op if the question is already saved)."""
    rows = _read_rows()
    key = norm(question)
    if any(norm(r.get("question_text")) == key for r in rows):
        return
    rows.append({
        "question_text": question.strip(), "answer": answer, "field_type": field_type,
        "created_at": datetime.now().isoformat(timespec="seconds"), "source": source,
        "options": " | ".join(options or []),
    })
    _write_rows(rows)


def llm_answer(question, field_type, options):
    """Ask the claude CLI to answer from resume.txt. Returns '' on failure."""
    try:
        with open(RESUME_TXT, encoding="utf-8") as f:
            resume = f.read()
    except OSError:
        logger.warning("  resume.txt missing; cannot use LLM")
        return ""
    extra = "\n".join(f"{k}: {v}" for k, v in PROFILE.items() if v)
    if options:
        fmt = ("Choose from these options and reply with the option text copied EXACTLY: "
               + " || ".join(options)
               + (". Several may be selected; separate them with ' | '." if field_type == "checkbox" else ". Reply with exactly one."))
    elif field_type == "number":
        fmt = "Reply with a single number only."
    else:
        fmt = "Reply with the short answer text only (one line unless a long answer is clearly required)."
    prompt = (
        "You are filling out a job application's recruiter screening question on behalf of the candidate "
        "below. Use ONLY the resume/profile for facts.\n"
        "Rules: answer in first person as the candidate; no explanations, no quotes, no markdown. "
        "For experience-in-X questions give the years from the resume (0 only if truly unrelated). "
        "For yes/no willingness, availability, relocation, interview, or eligibility questions answer Yes "
        "(candidate is based in Hyderabad and is actively job hunting). "
        "If a salary or notice-period value is not in the profile, give a realistic, modest value "
        "(notice period: 30 days; expected CTC: a reasonable raise over a typical AI engineer salary in India, in LPA).\n\n"
        f"=== RESUME ===\n{resume}\n=== PROFILE OVERRIDES ===\n{extra}\n\n"
        f"=== QUESTION ===\n{question}\n\n{fmt}\nAnswer:"
    )
    try:
        # run from a temp dir so no project CLAUDE.md/context is loaded
        proc = subprocess.run(
            ["claude", "-p", "--model", LLM_MODEL], input=prompt, capture_output=True,
            text=True, encoding="utf-8", timeout=LLM_TIMEOUT, cwd=tempfile.gettempdir())
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning(f"  LLM call failed: {e}")
        return ""
    ans = (proc.stdout or "").strip().strip('"').strip()
    ans = re.sub(r"^answer\s*:\s*", "", ans, flags=re.I)
    return ans.splitlines()[0].strip() if ans and field_type != "textarea" else ans


def find_answer(question, saved, field_type="text", options=None):
    """Return (answer, source). source is 'saved' | 'rule' | 'llm'; answer '' when none."""
    q = norm(question)
    if q in saved:
        return saved[q], "saved"
    close = difflib.get_close_matches(q, list(saved), n=1, cutoff=0.95)
    if close:
        return saved[close[0]], "saved"
    ans = rule_answer(question)
    if ans:
        return ans, "rule"
    ans = llm_answer(question, field_type, options)
    return ans, "llm" if ans else ""


# ---------------------------------------------------------------------------
# Option matching for radio / select / checkbox
# ---------------------------------------------------------------------------
def _range_contains(option, number):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", option)
    if m:
        return float(m.group(1)) <= number <= float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", option)
    if m:
        return number >= float(m.group(1))
    return False


def match_option(answer, options):
    """Return the index of the option best matching `answer`, or -1."""
    a = norm(answer)
    opts = [norm(o) for o in options]
    for i, o in enumerate(opts):
        if o == a:
            return i
    if a in ("yes", "y", "true"):
        for i, o in enumerate(opts):
            if o.startswith("yes"):
                return i
    if a in ("no", "n", "false"):
        for i, o in enumerate(opts):
            if o.startswith("no"):
                return i
    if re.fullmatch(r"\d+(\.\d+)?", a):
        for i, o in enumerate(opts):
            if _range_contains(o, float(a)):
                return i
    for i, o in enumerate(opts):
        if o and (a in o or o in a):
            return i
    best = difflib.get_close_matches(a, opts, n=1, cutoff=0.7)
    return opts.index(best[0]) if best else -1


# ---------------------------------------------------------------------------
# Page inspection (generic: works without knowing Naukri's exact markup)
# ---------------------------------------------------------------------------
JS_COLLECT = r"""
document.querySelectorAll('[data-qa-idx]').forEach(e => e.removeAttribute('data-qa-idx'));
const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const skip = e => e.closest('header,nav,footer,[class*="nI-gNb"],[id*="gnb"]');
let n = 0;
const tag = e => { e.setAttribute('data-qa-idx', n); return n++; };
const bots = [...document.querySelectorAll('.chatbot_MessageContainer .botMsg')]
  .map(b => (b.innerText || '').trim()).filter(Boolean);
function questionOf(el, strip) {
  // Naukri chatbot: the question is the most recent bot message
  if (bots.length && el.closest('[class*="chatbot"], .singleselect-radiobutton, .footerWrapper'))
    return bots[bots.length - 1].slice(0, 300);
  const aria = el.getAttribute('aria-label');
  if (aria && aria.length > 5) return aria;
  let node = el.parentElement;
  for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
    let t = node.innerText || '';
    strip.forEach(s => { if (s) t = t.split(s).join(' '); });
    const lines = t.split('\n').map(x => x.trim()).filter(x => x.length > 2);
    if (lines.length) {
      const q = lines.filter(l => l.includes('?'));
      return (q.length ? q[q.length - 1] : lines[lines.length - 1]).slice(0, 300);
    }
  }
  return el.getAttribute('placeholder') || '';
}
function labelOf(el) {
  if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) return l.innerText.trim(); }
  const l = el.closest('label'); if (l) return l.innerText.trim();
  return (el.parentElement ? el.parentElement.innerText : '').trim();
}
const out = [], groups = {};
document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach(el => {
  if (skip(el)) return;
  const type = (el.getAttribute('type') || '').toLowerCase();
  if (['hidden', 'file', 'submit', 'button', 'image', 'search'].includes(type)) return;
  if (/search/i.test(el.getAttribute('placeholder') || '')) return;
  if (type === 'radio' || type === 'checkbox') {
    const host = el.closest('label') || el.parentElement;
    if (!vis(el) && !(host && vis(host))) return;
    const key = type + ':' + (el.name || (el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.className : ''));
    (groups[key] = groups[key] || {kind: type, els: []}).els.push(el);
    return;
  }
  if (!vis(el) || el.disabled || el.readOnly) return;
  let kind = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.isContentEditable ? 'text' : (type === 'number' ? 'number' : 'text'));
  const options = kind === 'select' ? [...el.options].map(o => o.text.trim()).filter(t => t && !/^select/i.test(t)) : [];
  out.push({idx: tag(el), kind, question: questionOf(el, []), options, value: el.value || el.innerText || ''});
});
Object.values(groups).forEach(g => {
  const labels = g.els.map(labelOf);
  out.push({idx: g.els.map(tag), kind: g.kind, question: questionOf(g.els[0], labels), options: labels,
            value: g.els.some(e => e.checked) ? 'checked' : ''});
});
return out;
"""

JS_CLICK_SUBMIT = r"""
const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const re = /^(save|submit|submit and apply|next|send|continue|proceed|done|apply|apply now|confirm)\b/i;
const sendCls = /send|submit|save/i;
const c = [...document.querySelectorAll('button, [role="button"], input[type="submit"], [class*="sendMsg"], [class*="SendBtn"], [class*="sendBtn"]')]
  .filter(b => vis(b) && !b.disabled && !b.closest('header,nav,footer,[class*="nI-gNb"]')
               && (re.test((b.innerText || b.value || '').trim())
                   || (b.closest('[class*="chatbot"]') && sendCls.test(b.className || ''))));
const inBot = c.filter(b => b.closest('[class*="chatbot"]'));
const pick = inBot.length ? inBot : c;
if (!pick.length) return '';
const b = pick[pick.length - 1]; b.click(); return (b.innerText || b.value || b.className || '').trim();
"""


def _collect_fields(driver):
    try:
        return driver.execute_script(JS_COLLECT) or []
    except WebDriverException as e:
        logger.debug(f"collect fields failed: {e}")
        return []


def _el(driver, idx):
    return driver.find_element(By.CSS_SELECTOR, f'[data-qa-idx="{idx}"]')


def _fill_field(driver, field, answer):
    """Fill one field/group. Returns True if the answer could be applied."""
    kind, idx = field["kind"], field["idx"]
    if kind in ("text", "number", "textarea"):
        el = _el(driver, idx)
        el.click()
        try:
            el.clear()
        except WebDriverException:
            driver.execute_script("arguments[0].innerText='';", el)
        el.send_keys(answer)
        if kind == "text" and el.get_attribute("contenteditable") == "true":
            el.send_keys(Keys.ENTER)  # chatbot input sends on Enter
        return True
    if kind == "select":
        sel = Select(_el(driver, idx))
        i = match_option(answer, field["options"])
        if i < 0:
            return False
        sel.select_by_visible_text(field["options"][i])
        return True
    # radio / checkbox group: idx is a list; several checkbox answers separated by '|'
    wanted = [a for a in answer.split("|")] if kind == "checkbox" else [answer]
    picked = [match_option(a, field["options"]) for a in wanted]
    picked = sorted({i for i in picked if i >= 0})
    if not picked:
        return False
    for i in picked:
        el = _el(driver, idx[i])
        driver.execute_script(
            "const e=arguments[0]; const l=e.closest('label')||(e.id&&document.querySelector('label[for=\"'+e.id+'\"]'));"
            "(l||e).click(); if(!e.checked) e.click();", el)
    return True


def _dump_debug(driver, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    try:
        with open(os.path.join(DEBUG_DIR, f"{name}_{stamp}.html"), "w", encoding="utf-8") as f:
            f.write(driver.execute_script("return document.documentElement.outerHTML"))
        driver.save_screenshot(os.path.join(DEBUG_DIR, f"{name}_{stamp}.png"))
    except WebDriverException:
        pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
QUICK_APPLY_XPATH = "//button[.//span[normalize-space()='Quick apply'] or normalize-space()='Quick apply']"
COMPANY_SITE_XPATH = "//button[contains(normalize-space(.),'Apply on company site')]"


def _path(url):
    return url.split("?")[0].rstrip("/")


def _chat_open(driver):
    """True while Naukri's screening-question chatbot drawer is visible."""
    try:
        return bool(driver.execute_script(
            "return [...document.querySelectorAll('.chatbot_DrawerContentWrapper, .chatbot_MessageContainer')]"
            ".some(e => e.getBoundingClientRect().width > 0)"))
    except WebDriverException:
        return False


def _chatbot_done(driver):
    try:
        return bool(driver.execute_script(
            "return [...document.querySelectorAll('.botMsg')].some("
            "b => /thank you for your responses|successfully applied|application (has been )?submitted/i.test(b.innerText))"))
    except WebDriverException:
        return False


def quick_apply(driver, link, timeout=60):
    """
    Click Quick apply on an already-loaded job page and answer any questions.
    Returns one of: 'applied', 'already', 'external', 'quota', 'unanswered', 'failed'.
    """
    if driver.find_elements(By.XPATH, "//*[text()='Your daily quota has been expired.']"):
        return "quota"

    buttons = driver.find_elements(By.XPATH, QUICK_APPLY_XPATH)
    if not buttons:
        return "external" if driver.find_elements(By.XPATH, COMPANY_SITE_XPATH) else "failed"
    if not buttons[0].is_enabled():
        return "already"  # button is disabled once applied

    driver.execute_script("arguments[0].click()", buttons[0])
    clicked_at = time.time()
    saved = load_saved_answers()
    deadline = time.time() + timeout
    answered = {}          # normalised question -> loops spent waiting for the next one
    idle_since = time.time()

    while time.time() < deadline:
        time.sleep(1.5)
        try:
            if _path(driver.current_url) != _path(link):
                return "applied"  # Naukri redirects after a direct quick apply
            # The Quick apply button is ALSO disabled while the questionnaire drawer is open,
            # so only treat "disabled" as success once the drawer is gone (and give it time to open).
            btn = driver.find_elements(By.XPATH, QUICK_APPLY_XPATH)
            if time.time() - clicked_at > 5 and not _chat_open(driver):
                # drawer closed: applied if the button is disabled/gone or Naukri shows the post-apply page
                if not btn or not btn[0].is_enabled() or driver.execute_script(
                        "return /Similar opportunities|applied successfully/i.test(document.body.innerText)"):
                    return "applied"
            if driver.find_elements(By.XPATH, "//*[text()='Your daily quota has been expired.']"):
                return "quota"
        except WebDriverException:
            return "applied"  # page navigated away mid-check

        fields = _collect_fields(driver)
        if not fields:
            # Chatbot's closing message, or drawer gone after we already answered questions
            if _chatbot_done(driver) or (answered and not _chat_open(driver)):
                return "applied"
            if time.time() - idle_since > 12:
                logger.warning("  No success signal and no recognised question form; saving debug page")
                _dump_debug(driver, "unknown_state")
                return "failed"
            continue
        idle_since = time.time()

        progressed = False
        for field in fields:
            question = field["question"] or "(unlabelled field)"
            key = norm(question)
            if field["value"]:
                continue  # prefilled / already selected
            if key in answered:
                # Already answered; waiting for the chatbot to show the next question.
                answered[key] += 1
                if answered[key] in (4, 8):
                    logger.info("  Still on the same question, clicking submit again")
                    driver.execute_script(JS_CLICK_SUBMIT)
                elif answered[key] > 12:
                    logger.warning(f"  Stuck on question: {question}")
                    _dump_debug(driver, "stuck_question")
                    return "failed"
                continue

            options = field["options"]
            answer, source = find_answer(question, saved, field["kind"], options)
            try:
                filled = bool(answer) and _fill_field(driver, field, answer)
                if not filled and source != "llm":
                    # saved/rule answer didn't fit the options -> let the LLM choose an option
                    answer = llm_answer(question, field["kind"], options)
                    source = "llm"
                    filled = bool(answer) and _fill_field(driver, field, answer)
            except (NoSuchElementException, StaleElementReferenceException):
                # chatbot re-rendered between detection and fill (or the question changed): re-detect
                logger.debug("  field vanished while filling; re-detecting")
                break
            if not filled:
                logger.warning(f"  Could not answer: {question!r} (options={options})")
                save_answer(question, "", field["kind"], "unanswered", options)
                _dump_debug(driver, "unanswered")
                return "unanswered"
            logger.info(f"  Q: {question[:90]!r} -> {answer!r} [{source}]")
            save_answer(question, answer, field["kind"], source, options)
            answered[key] = 0
            progressed = True

        if progressed:
            time.sleep(1)
            clicked = driver.execute_script(JS_CLICK_SUBMIT)
            logger.info(f"  Submitted: {clicked or '(no submit button; assuming auto-send)'}")
            deadline = time.time() + timeout  # more questions may follow; LLM calls are slow

    _dump_debug(driver, "timeout")
    return "failed"
