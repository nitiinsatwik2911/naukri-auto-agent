"""Recommended-jobs mode: read the recommendations from Naukri's API, let you pick which
tabs to apply from (All, Top companies, Strong match, ...), then apply with the shared loop.

The page's five tabs are one API call; a tab is just a list of job ids (a "cluster") inside it."""
import json
import logging
import re
import sys

from . import config
from .browser import login_naukri
from .netapi import capture_request, fetch_json
from .pipeline import run_pipeline
from .results import load_history

logger = logging.getLogger(__name__)

BASE_URL = config.get("NAUKRI_BASE_URL")
PAGE_URL = config.get("RECO_PAGE_URL")
API_PATH = config.get("RECO_API_PATH")
API_HEADERS = config.get("RECO_API_HEADERS").split(",")
API_COUNT = config.get_int("RECO_COUNT")
PAGE_WAIT = config.get_int("RECO_PAGE_WAIT")
SKIP_COMPANY_APPLY = config.get_bool("RECO_SKIP_COMPANY_APPLY")
ALL_TAB = "all"  # the tab with no filter: every job in the response


# ---------------------------------------------------------------------------
# Pure helpers (no browser)
# ---------------------------------------------------------------------------
def parse_tabs(spec):
    """'all:All,top_company:Top companies' -> [('all', 'All'), ('top_company', 'Top companies')]."""
    tabs = []
    for part in spec.split(","):
        tab_id, _, label = part.partition(":")
        if tab_id.strip():
            tabs.append((tab_id.strip(), label.strip() or tab_id.strip()))
    return tabs


def parse_selection(text, count):
    """'3', '3,5', '2 4' or '2-4' -> unique 1-based numbers in the order given.
    Raises ValueError for empty input or numbers outside 1..count."""
    chosen = []
    for token in re.split(r"[,\s]+", text.strip()):
        if not token:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise ValueError(f"'{token}' is not a number")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        for number in range(start, end + 1):
            if not 1 <= number <= count:
                raise ValueError(f"{number} is not between 1 and {count}")
            if number not in chosen:
                chosen.append(number)
    if not chosen:
        raise ValueError("nothing selected")
    return chosen


def with_reco_count(body, count):
    """Return the request body (JSON text) with recoCount set to `count`."""
    data = json.loads(body) if body else {}
    data["recoCount"] = count
    return json.dumps(data, separators=(",", ":"))


def tab_jobs(response, tab_id):
    """Job dicts of one tab, in the response's order. Ids a tab lists but the response has no
    details for are returned separately as a count."""
    reco = response.get("recommendedClusters") or {}
    details = {job["jobId"]: job for job in reco.get("jobDetails", [])}
    if tab_id == ALL_TAB:
        return list(details.values()), 0
    ids = []
    for cluster in reco.get("clusters") or []:
        for group in [cluster] + (cluster.get("subClusters") or []):
            if tab_id in (group.get("clusterId"), group.get("subClusterId")):
                ids.extend(group.get("jobIds") or [])
    ids = list(dict.fromkeys(ids))
    return [details[i] for i in ids if i in details], sum(1 for i in ids if i not in details)


def pick_links(response, tab_ids, skip_company_apply=True, skip_links=()):
    """Links of the jobs in the chosen tabs (in tab order, no duplicates), leaving out jobs
    already applied to, company-site jobs (optional) and links in `skip_links`."""
    skip = set(skip_links)
    links = []
    for tab_id in tab_ids:
        for job in tab_jobs(response, tab_id)[0]:
            path = job.get("jdURL")
            if not path or job.get("applied") or job.get("isApplied"):
                continue
            if skip_company_apply and job.get("jobApplyType") == "companyApply":
                continue
            link = path if path.startswith("http") else BASE_URL.rstrip("/") + path
            if link not in skip and link not in links:
                links.append(link)
    return links


# ---------------------------------------------------------------------------
# Browser flow
# ---------------------------------------------------------------------------
def _choose_tabs(response, tabs, skip, preset):
    """Show the tab menu and return the chosen tab ids (from `preset`, e.g. '3,5', or by asking)."""
    print("\nRecommended tabs (jobs you can apply to now):")
    for number, (tab_id, label) in enumerate(tabs, 1):
        usable = len(pick_links(response, [tab_id], SKIP_COMPANY_APPLY, skip))
        unread = tab_jobs(response, tab_id)[1]
        note = f"  (+{unread} listed without details, not usable)" if unread else ""
        print(f"  {number}. {label}: {usable}{note}")

    text = preset
    while True:
        if text is None:
            if not sys.stdin.isatty():
                raise SystemExit("No tab chosen: pass --tabs, for example: python cli.py recommended --tabs 3,5")
            text = input("Choose one or more tabs, e.g. 3 or 3,5: ")
        try:
            numbers = parse_selection(text, len(tabs))
            break
        except ValueError as e:
            if preset is not None:
                raise SystemExit(f"Invalid --tabs: {e}")
            print(f"  {e}. Try again.")
            text = None
    chosen = [tabs[n - 1] for n in numbers]
    logger.info("Tabs: " + ", ".join(label for _, label in chosen))
    return [tab_id for tab_id, _ in chosen]


def run(tabs_arg=None):
    """Entry point for recommended mode. `tabs_arg` (like '3,5') skips the question."""
    if not config.get("NAUKRI_EMAIL") or not config.get("NAUKRI_PASSWORD"):
        logger.error("NAUKRI_EMAIL / NAUKRI_PASSWORD are not set in .env")
        return
    tabs = parse_tabs(config.get("RECO_TABS"))
    if not tabs:
        logger.error("RECO_TABS is empty in .env")
        return

    def collect(driver):
        login_naukri(driver)
        request = capture_request(driver, PAGE_URL, API_PATH, PAGE_WAIT, API_HEADERS)
        if request is None:
            return []
        try:
            response = fetch_json(driver, request, body=with_reco_count(request["body"], API_COUNT))
        except ValueError:
            logger.error("The recommendations response was not readable")
            return []
        skip = load_history()
        chosen = _choose_tabs(response, tabs, skip, tabs_arg)
        return pick_links(response, chosen, SKIP_COMPANY_APPLY, skip)

    run_pipeline(collect, "Nothing usable in the chosen tabs.", logged_in=True, capture_network=True)
