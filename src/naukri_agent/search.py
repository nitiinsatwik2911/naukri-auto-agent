"""Keyword-search mode: open one tab per keyword/page, collect job links, then apply."""
import logging
import time

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from . import config
from .apply import apply_to_jobs
from .browser import create_edge_driver, login_naukri
from .filters import build_filter_urls
from .jobapi import fetch_filter_job_links
from .results import RESULTS_CSV, load_history, save_results

logger = logging.getLogger(__name__)

NAUKRI_EMAIL = config.get('NAUKRI_EMAIL')
NAUKRI_PASSWORD = config.get('NAUKRI_PASSWORD')
FIRSTNAME = config.get('FIRSTNAME')
LASTNAME = config.get('LASTNAME')
KEYWORDS = [kw.strip() for kw in config.get('KEYWORDS').split(',') if kw.strip()]
LOCATION = config.get('LOCATION')
MAX_APPLICATIONS = config.get_int('MAX_APPLICATIONS')
PAGES_PER_KEYWORD = config.get_int('PAGES_PER_KEYWORD')
FILTER_URL = config.get('FILTER_URL')
FILTER_DROP_PARAMS = [p.strip() for p in config.get('FILTER_DROP_PARAMS').split(',') if p.strip()]


def validate_config(need_keywords=True):
    """Check that required configuration values are set."""
    errors = []
    if not NAUKRI_EMAIL:
        errors.append("NAUKRI_EMAIL is not set in .env")
    if not NAUKRI_PASSWORD:
        errors.append("NAUKRI_PASSWORD is not set in .env")
    if need_keywords and not KEYWORDS:
        errors.append("KEYWORDS is not set in .env (comma-separated job roles)")
    if not FIRSTNAME:
        errors.append("FIRSTNAME is not set in .env")
    if not LASTNAME:
        errors.append("LASTNAME is not set in .env")
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Please copy .env.example to .env and fill in your details.")
        return False
    return True


def build_search_urls():
    """
    Build all search URLs for every keyword and page combination.
    Naukri.com updated URL format: /{keyword}-jobs-in-{location}
    Returns a list of (keyword, url) tuples.
    """
    urls = []
    for keyword in KEYWORDS:
        keyword_slug = keyword.lower().replace(' ', '-')
        for page_num in range(1, PAGES_PER_KEYWORD + 1):
            if not LOCATION:
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}"
            else:
                location_slug = LOCATION.lower().replace(' ', '-')
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}-{page_num}"
            urls.append((keyword, url))
    return urls


def open_tabs_parallel(driver, search_urls):
    """
    Open all search URLs in parallel browser tabs.
    The first URL opens in the current tab; the rest open in new tabs.
    Returns the original window handle.
    """
    original_window = driver.current_window_handle

    if not search_urls:
        return original_window

    # Open first URL in current tab
    keyword, first_url = search_urls[0]
    logger.info(f"[Tab: Main] Opening: {first_url}")
    driver.get(first_url)
    time.sleep(3)

    # Open remaining URLs in new tabs
    for keyword, url in search_urls[1:]:
        logger.info(f"[Tab: New] Opening: {url}")
        driver.switch_to.new_window('tab')
        driver.get(url)
        time.sleep(2)

    # Switch back to the original tab
    driver.switch_to.window(original_window)
    return original_window


def collect_job_links_from_tab(driver, window_handle):
    """
    Switch to a specific tab, scrape job links from the page.
    Uses updated Naukri.com selectors (as of 2026 redesign).

    Current HTML structure for job cards:
        <div class="srp-jobtuple-wrapper" data-job-id="...">
          <div class="cust-job-tuple layout-wrapper lay-2 sjw__tuple">
            <div class="row1">
              <h2><a class="title " href="https://...">Job Title</a></h2>
            </div>
          </div>
        </div>
    """
    links = []
    try:
        driver.switch_to.window(window_handle)
        time.sleep(3)  # Wait for page to fully render

        soup = BeautifulSoup(driver.page_source, 'html5lib')

        # New selector: find all job tuple wrappers
        job_wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper')
        logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (srp-jobtuple-wrapper)")

        if not job_wrappers:
            # Fallback: try the older cust-job-tuple class
            job_wrappers = soup.find_all('div', class_='cust-job-tuple')
            logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (cust-job-tuple fallback)")

        for job_wrapper in job_wrappers:
            # Find the title link - new selector is a.title (class="title ")
            title_link = job_wrapper.find('a', class_='title')
            if title_link and title_link.get('href'):
                href = title_link.get('href')
                # Ensure full URL
                if href.startswith('/'):
                    href = 'https://www.naukri.com' + href
                links.append(href)

    except WebDriverException as e:
        logger.warning(f"[Tab] Error reading tab: {e}")

    return links


def collect_all_jobs_parallel(driver, search_urls):
    """
    Open all keyword search pages in parallel tabs and collect job links from each.
    Returns a deduplicated list of job URLs.
    """
    logger.info("=" * 50)
    logger.info(f"Opening {len(search_urls)} search pages in parallel tabs...")
    logger.info("=" * 50)

    # Open all search URLs in parallel tabs
    original_window = open_tabs_parallel(driver, search_urls)

    # Collect job links from each tab
    all_links = []
    window_handles = driver.window_handles
    logger.info(f"Collecting job links from {len(window_handles)} tabs...")

    for handle in window_handles:
        tab_links = collect_job_links_from_tab(driver, handle)
        all_links.extend(tab_links)

    # Close all extra tabs and return to main
    logger.info("Closing search tabs...")
    for handle in window_handles:
        if handle != original_window:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except WebDriverException:
                pass
    driver.switch_to.window(original_window)

    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    logger.info(f"Total unique job links collected: {len(unique_links)}")
    return unique_links


def run():
    """Entry point for keyword-search mode."""
    if not validate_config():
        return
    logger.info(f"Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION or 'Anywhere'}")
    logger.info(f"Pages per keyword: {PAGES_PER_KEYWORD}")
    search_urls = build_search_urls()
    logger.info(f"Total search pages to open: {len(search_urls)}")

    # Collected BEFORE logging in: the logged-in search page renders no job links
    _run_pipeline(lambda driver: collect_all_jobs_parallel(driver, search_urls),
                  "Check your keywords and location.")


def run_filter():
    """Entry point for filter mode: read the jobs of FILTER_URL via the search API and apply."""
    if not validate_config(need_keywords=False):
        return
    if not FILTER_URL:
        logger.error("FILTER_URL is not set in .env (paste a Naukri search URL with your filters)")
        return
    try:
        page_url = build_filter_urls(FILTER_URL, 1, FILTER_DROP_PARAMS)[0][1]
    except ValueError as e:
        logger.error(str(e))
        return
    logger.info(f"Filter URL: {page_url}")

    def collect(driver):
        login_naukri(driver)  # the logged-in view is what the API returns
        return fetch_filter_job_links(driver, page_url)

    _run_pipeline(collect, "Check FILTER_URL in .env.", logged_in=True, capture_network=True)


def _run_pipeline(collect, empty_hint, logged_in=False, capture_network=False):
    """collect(driver) -> job links; then skip settled jobs, log in (unless already) and apply."""
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply Bot (Edge Edition - 2026 Update)")
    logger.info("=" * 50)
    logger.info(f"Max applications: {MAX_APPLICATIONS}")

    driver = None
    try:
        driver = create_edge_driver(capture_network=capture_network)

        job_links = collect(driver)
        if not job_links:
            logger.warning(f"No job links found. {empty_hint}")
            return

        # Drop jobs settled in earlier runs (applied / already applied / external site)
        done = load_history()
        fresh = [link for link in job_links if link not in done]
        logger.info(f"Skipping {len(job_links) - len(fresh)} jobs from earlier runs; "
                    f"{len(fresh)} new to process")
        job_links = fresh
        if not job_links:
            logger.info("Nothing new to apply to.")
            return

        if not logged_in:
            login_naukri(driver)

        applied, failed, applied_list = apply_to_jobs(driver, job_links, MAX_APPLICATIONS)
        save_results(applied_list)

        logger.info("=" * 50)
        logger.info("APPLICATION SUMMARY")
        logger.info(f"  Successfully applied: {applied}")
        logger.info(f"  Failed/Skipped:      {failed}")
        logger.info(f"  Total processed:     {applied + failed}")
        logger.info(f"  Results saved to:    {RESULTS_CSV}")
        logger.info("=" * 50)

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass
