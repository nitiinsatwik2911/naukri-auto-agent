"""Filter mode: read a filtered Naukri search through the site's own search API,
page by page, from a logged-in browser (see netapi.py)."""
import logging

from . import config
from .filters import job_links, with_page
from .netapi import capture_request, fetch_json

logger = logging.getLogger(__name__)

BASE_URL = config.get("NAUKRI_BASE_URL")
API_PATH = config.get("FILTER_API_PATH")
API_HEADERS = config.get("FILTER_API_HEADERS").split(",")
API_WAIT = config.get_int("FILTER_API_WAIT")
MAX_PAGES = config.get_int("FILTER_MAX_PAGES")


def fetch_filter_job_links(driver, page_url):
    """Open `page_url` (the filtered search page) and return all job links across its pages."""
    request = capture_request(driver, page_url, API_PATH, API_WAIT, API_HEADERS)
    if request is None:
        return []

    links = []
    for page in range(1, MAX_PAGES + 1):
        try:
            found = job_links(fetch_json(driver, request, url=with_page(request["url"], page)), BASE_URL)
        except ValueError:
            logger.warning(f"Page {page}: unreadable API response")
            break
        logger.info(f"API page {page}: {len(found)} jobs")
        if not found:
            break
        links.extend(link for link in found if link not in links)
    return links
