"""Read a filtered Naukri search through the site's own search API.

The logged-in search page renders no job links, so instead the page's own API request
(URL + auth headers) is captured from the browser's network log and replayed page by page.
The browser must be created with capture_network=True and already be logged in."""
import json
import logging
import time

from . import config
from .filters import find_search_request, job_links, pick_headers, with_page

logger = logging.getLogger(__name__)

BASE_URL = config.get("NAUKRI_BASE_URL")
API_PATH = config.get("FILTER_API_PATH")
API_HEADERS = config.get("FILTER_API_HEADERS").split(",")
API_WAIT = config.get_int("FILTER_API_WAIT")
MAX_PAGES = config.get_int("FILTER_MAX_PAGES")

_FETCH_JS = """
const [url, headers, done] = arguments;
fetch(url, {headers: headers, credentials: 'include'})
  .then(r => r.text()).then(done).catch(e => done('ERR ' + e));
"""


def fetch_filter_job_links(driver, page_url):
    """Open `page_url` (the filtered search page) and return all job links across its pages."""
    driver.get_log("performance")  # drop older entries
    driver.get(page_url)
    time.sleep(API_WAIT)
    request = find_search_request(driver.get_log("performance"), API_PATH)
    if request is None:
        logger.error(f"Search API call ({API_PATH}) not seen on the page; cannot read jobs")
        return []
    api_url, headers = request
    headers = pick_headers(headers, API_HEADERS)
    driver.set_script_timeout(30)

    links = []
    for page in range(1, MAX_PAGES + 1):
        raw = driver.execute_async_script(_FETCH_JS, with_page(api_url, page), headers)
        try:
            found = job_links(json.loads(raw), BASE_URL)
        except ValueError:
            logger.warning(f"Page {page}: unreadable API response: {raw[:100]!r}")
            break
        logger.info(f"API page {page}: {len(found)} jobs")
        if not found:
            break
        links.extend(link for link in found if link not in links)
    return links
