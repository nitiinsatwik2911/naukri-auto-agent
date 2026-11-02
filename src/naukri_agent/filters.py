"""Filter mode: turn one Naukri search URL (copied from the browser, filters included)
into the list of result-page URLs to scrape."""
import json
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


def build_filter_urls(filter_url, pages, drop_params):
    """Return [(label, url), ...] for result pages 1..pages of `filter_url`.

    Page n > 1 is the same URL with '-n' appended to the path (Naukri's scheme), and all
    query filters are kept (repeated keys such as wfhType survive). `drop_params` is an
    iterable of tracking parameters to remove.
    """
    parts = urlsplit(filter_url.strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"FILTER_URL is not a full URL: {filter_url!r}")
    drop = set(drop_params)
    # quote (%20), not quote_plus ('+'): Naukri reads a '+' in k= literally and finds fewer jobs
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in drop],
                      quote_via=quote)
    path = parts.path.rstrip("/")
    urls = []
    for page in range(1, pages + 1):
        page_path = path if page == 1 else f"{path}-{page}"
        urls.append((f"filter p{page}", urlunsplit((parts.scheme, parts.netloc, page_path, query, ""))))
    return urls


# ---------------------------------------------------------------------------
# Search-API helpers (pure): the page's own jobapi request is replayed per page
# ---------------------------------------------------------------------------
def find_search_request(log_entries, api_path):
    """Return (url, headers) of the last network request to `api_path` in Chrome
    performance-log entries, or None. Request header names are lower-cased."""
    found = None
    for entry in log_entries:
        message = json.loads(entry["message"])["message"]
        if message.get("method") == "Network.requestWillBeSent":
            request = message["params"]["request"]
            if api_path in request["url"]:
                found = (request["url"], {k.lower(): v for k, v in request["headers"].items()})
    return found


def pick_headers(headers, names):
    """Keep only the headers listed in `names` (case-insensitive)."""
    wanted = {n.strip().lower() for n in names if n.strip()}
    return {k: v for k, v in headers.items() if k.lower() in wanted}


def with_page(api_url, page):
    """Return `api_url` with its pageNo parameter set to `page`."""
    parts = urlsplit(api_url)
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "pageNo"]
    pairs.append(("pageNo", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs, quote_via=quote), ""))


def job_links(response, base_url):
    """Absolute job URLs (from jdURL) in one search-API response; [] for an error response."""
    links = []
    for job in response.get("jobDetails", []):
        path = job.get("jdURL")
        if path:
            links.append(path if path.startswith("http") else base_url.rstrip("/") + path)
    return links
