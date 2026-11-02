"""Apply to jobs: Quick-apply orchestration plus the per-run loop."""
import logging
import time
from urllib.parse import urlsplit

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By

from . import chatbot
from .answers import find_answer, llm_answer, load_saved_answers, norm, save_answer
from .results import record_history

logger = logging.getLogger(__name__)


# Pro accounts show "Quick apply"; free accounts show a plain "Apply" button (#apply-button)
QUICK_APPLY_XPATH = ("//button[.//span[normalize-space()='Quick apply'] or normalize-space()='Quick apply']"
                     " | //button[@id='apply-button']")
COMPANY_SITE_XPATH = "//button[contains(normalize-space(.),'Apply on company site')]"
# Free accounts show an "Applied" label (no button) once you have applied
ALREADY_APPLIED_XPATH = "//*[@id='already-applied']"


def _path(url):
    return url.split("?")[0].rstrip("/")


def _already_applied(driver):
    return any(e.is_displayed() for e in driver.find_elements(By.XPATH, ALREADY_APPLIED_XPATH))


def _close_extra_tabs(driver, keep):
    """Close every tab except `keep` (an Apply that opens the company site in a new tab)."""
    for handle in driver.window_handles:
        if handle != keep:
            driver.switch_to.window(handle)
            driver.close()
    driver.switch_to.window(keep)


def quick_apply(driver, link, timeout=60):
    """
    Click Quick apply / Apply on an already-loaded job page and answer any questions.
    Returns one of: 'applied', 'already', 'external', 'quota', 'unanswered', 'failed'.
    """
    if driver.find_elements(By.XPATH, "//*[text()='Your daily quota has been expired.']"):
        return "quota"

    if _already_applied(driver):
        return "already"
    buttons = driver.find_elements(By.XPATH, QUICK_APPLY_XPATH)
    if not buttons:
        return "external" if driver.find_elements(By.XPATH, COMPANY_SITE_XPATH) else "failed"
    if not buttons[0].is_enabled():
        return "already"  # button is disabled once applied

    main_tab = driver.current_window_handle
    driver.execute_script("arguments[0].click()", buttons[0])
    clicked_at = time.time()
    saved = load_saved_answers()
    deadline = time.time() + timeout
    answered = {}          # normalised question -> loops spent waiting for the next one
    idle_since = time.time()

    while time.time() < deadline:
        time.sleep(1.5)
        try:
            if len(driver.window_handles) > 1:
                _close_extra_tabs(driver, main_tab)
                return "external"  # Apply opened the company's own site in a new tab
            if _path(driver.current_url) != _path(link):
                # Naukri redirects after a direct apply; landing on another site means external
                same_site = urlsplit(driver.current_url).netloc == urlsplit(link).netloc
                return "applied" if same_site else "external"
            # The Quick apply button is ALSO disabled while the questionnaire drawer is open,
            # so only treat "disabled" as success once the drawer is gone (and give it time to open).
            btn = driver.find_elements(By.XPATH, QUICK_APPLY_XPATH)
            if time.time() - clicked_at > 5 and not chatbot.chat_open(driver):
                # drawer closed: applied if the button is disabled/gone or Naukri shows the post-apply page
                if not btn or not btn[0].is_enabled() or _already_applied(driver) or driver.execute_script(
                        "return /Similar opportunities|applied successfully/i.test(document.body.innerText)"):
                    return "applied"
            if driver.find_elements(By.XPATH, "//*[text()='Your daily quota has been expired.']"):
                return "quota"
        except WebDriverException:
            return "applied"  # page navigated away mid-check

        fields = chatbot.collect_fields(driver)
        if not fields:
            # Chatbot's closing message, or drawer gone after we already answered questions
            if chatbot.chatbot_done(driver) or (answered and not chatbot.chat_open(driver)):
                return "applied"
            if time.time() - idle_since > 12:
                logger.warning("  No success signal and no recognised question form; saving debug page")
                chatbot.dump_debug(driver, "unknown_state")
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
                    chatbot.click_submit(driver)
                elif answered[key] > 12:
                    logger.warning(f"  Stuck on question: {question}")
                    chatbot.dump_debug(driver, "stuck_question")
                    return "failed"
                continue

            options = field["options"]
            answer, source = find_answer(question, saved, field["kind"], options)
            try:
                filled = bool(answer) and chatbot.fill_field(driver, field, answer)
                if not filled and source != "llm":
                    # saved/rule answer didn't fit the options -> let the LLM choose an option
                    answer = llm_answer(question, field["kind"], options)
                    source = "llm"
                    filled = bool(answer) and chatbot.fill_field(driver, field, answer)
            except (NoSuchElementException, StaleElementReferenceException):
                # chatbot re-rendered between detection and fill (or the question changed): re-detect
                logger.debug("  field vanished while filling; re-detecting")
                break
            if not filled:
                logger.warning(f"  Could not answer: {question!r} (options={options})")
                save_answer(question, "", field["kind"], "unanswered", options)
                chatbot.dump_debug(driver, "unanswered")
                return "unanswered"
            logger.info(f"  Q: {question[:90]!r} -> {answer!r} [{source}]")
            save_answer(question, answer, field["kind"], source, options)
            answered[key] = 0
            progressed = True

        if progressed:
            time.sleep(1)
            clicked = chatbot.click_submit(driver)
            logger.info(f"  Submitted: {clicked or '(no submit button; assuming auto-send)'}")
            deadline = time.time() + timeout  # more questions may follow; LLM calls are slow

    chatbot.dump_debug(driver, "timeout")
    return "failed"


def apply_to_jobs(driver, job_links, max_applications):
    """
    Visit each job link and Quick-apply, answering any screening questions
    (see answer_bot.py). Returns (applied_count, failed_count, applied_list).
    """
    applied = 0
    failed = 0
    applied_list = {'passed': [], 'failed': []}

    logger.info("=" * 50)
    logger.info(f"Starting job applications (max: {max_applications})...")
    logger.info("=" * 50)

    for i, link in enumerate(job_links, 1):
        if applied >= max_applications:
            logger.info(f"Reached max application limit ({max_applications}). Stopping.")
            break

        logger.info(f"[{i}/{len(job_links)}] Visiting job: {link}")
        try:
            driver.get(link)
            time.sleep(4)
            status = quick_apply(driver, link)
        except WebDriverException as e:
            logger.warning(f"  ✗ Browser error: {e}")
            status = 'failed'

        if status != 'quota':
            record_history(link, status)

        if status == 'applied':
            applied += 1
            applied_list['passed'].append(link)
            logger.info(f"  ✓ Applied! Total: {applied}")
        elif status == 'quota':
            logger.info("Daily quota expired. Stopping.")
            break
        else:
            failed += 1
            applied_list['failed'].append(link)
            reason = {
                'already': 'already applied',
                'external': 'external company-site application (skipped)',
                'unanswered': 'unanswered question(s) logged to application_answers.csv',
            }.get(status, 'could not complete application')
            logger.warning(f"  ✗ Skipped: {reason}")

    return applied, failed, applied_list
