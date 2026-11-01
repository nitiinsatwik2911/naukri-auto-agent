"""
Naukri Auto-Apply Bot - Microsoft Edge Version (Updated for Naukri.com 2026)
================================================================================
Automates job applications on Naukri.com using Selenium with Edge browser.
Opens each job keyword search in a separate tab for faster collection.

Usage:
    1. Copy .env.example to .env and fill in your details
    2. pip install -r requirements.txt
    3. python Naukri-Edge.py

Requirements:
    - Edge browser installed
    - Dependencies from requirements.txt
"""

import os
import time
import logging
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
from answer_bot import quick_apply
from browser import create_edge_driver, login_naukri

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

# --- Naukri Credentials ---
NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL', '')
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD', '')

# --- Personal Details ---
FIRSTNAME = os.getenv('FIRSTNAME', '')
LASTNAME = os.getenv('LASTNAME', '')

# --- Job Search ---
KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', '').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', '').strip()

# --- Limits ---
MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '2'))

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def validate_config():
    """Check that required configuration values are set."""
    errors = []
    if not NAUKRI_EMAIL:
        errors.append("NAUKRI_EMAIL is not set in .env")
    if not NAUKRI_PASSWORD:
        errors.append("NAUKRI_PASSWORD is not set in .env")
    if not KEYWORDS:
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


def apply_to_jobs(driver, job_links):
    """
    Visit each job link and Quick-apply, answering any screening questions
    (see answer_bot.py). Returns (applied_count, failed_count, applied_list).
    """
    applied = 0
    failed = 0
    applied_list = {'passed': [], 'failed': []}

    logger.info("=" * 50)
    logger.info(f"Starting job applications (max: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, link in enumerate(job_links, 1):
        if applied >= MAX_APPLICATIONS:
            logger.info(f"Reached max application limit ({MAX_APPLICATIONS}). Stopping.")
            break

        logger.info(f"[{i}/{len(job_links)}] Visiting job: {link}")
        try:
            driver.get(link)
            time.sleep(4)
            status = quick_apply(driver, link)
        except WebDriverException as e:
            logger.warning(f"  ✗ Browser error: {e}")
            status = 'failed'

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


def save_results(applied_list):
    """Save applied/failed links to CSV."""
    csv_file = "naukriapplied.csv"
    final_dict = {k: pd.Series(v) for k, v in applied_list.items()}
    df = pd.DataFrame.from_dict(final_dict)
    df.to_csv(csv_file, index=False)
    logger.info(f"Results saved to {csv_file}")


def main():
    """Main entry point for the bot."""
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply Bot (Edge Edition - 2026 Update)")
    logger.info("=" * 50)

    if not validate_config():
        return

    logger.info(f"Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION or 'Anywhere'}")
    logger.info(f"Max applications: {MAX_APPLICATIONS}")
    logger.info(f"Pages per keyword: {PAGES_PER_KEYWORD}")

    driver = None
    try:
        # Initialize browser
        driver = create_edge_driver()

        # Build all search URLs
        search_urls = build_search_urls()
        logger.info(f"Total search pages to open: {len(search_urls)}")

        # Collect all job links in parallel (multi-tab) BEFORE logging in:
        # the logged-in search page uses a new card layout without links.
        job_links = collect_all_jobs_parallel(driver, search_urls)

        if not job_links:
            logger.warning("No job links found. Check your keywords and location.")
            return

        # Login, then apply
        login_naukri(driver)

        # Apply to jobs
        applied, failed, applied_list = apply_to_jobs(driver, job_links)

        # Save results
        save_results(applied_list)

        # Summary
        logger.info("=" * 50)
        logger.info("APPLICATION SUMMARY")
        logger.info(f"  Successfully applied: {applied}")
        logger.info(f"  Failed/Skipped:      {failed}")
        logger.info(f"  Total processed:     {applied + failed}")
        logger.info(f"  Results saved to:    naukriapplied.csv")
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


if __name__ == "__main__":
    main()