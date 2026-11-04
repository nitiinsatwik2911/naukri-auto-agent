from naukri_agent.filters import build_filter_urls

URL = "https://www.naukri.com/ai-engineer-jobs?sort=r&wfhType=0&wfhType=3&experience=4&k=ai%20engineer&nignbevent_src=jobsearchDeskGNB"


def test_pages_and_filters_kept():
    urls = [u for _, u in build_filter_urls(URL, 2, ["nignbevent_src"])]
    assert urls[0] == "https://www.naukri.com/ai-engineer-jobs?sort=r&wfhType=0&wfhType=3&experience=4&k=ai%20engineer"
    assert urls[1].startswith("https://www.naukri.com/ai-engineer-jobs-2?sort=r&wfhType=0&wfhType=3")


def test_tracking_param_dropped():
    assert all("nignbevent_src" not in u for _, u in build_filter_urls(URL, 2, ["nignbevent_src"]))


def test_invalid_url():
    try:
        build_filter_urls("ai-engineer-jobs", 1, [])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# --- search-API helpers -------------------------------------------------------
import json

from naukri_agent.filters import find_request, job_links, pick_headers, with_page

API = "https://www.naukri.com/jobapi/v3/search?noOfResults=20&keyword=ai%20engineer&pageNo=1&src=directSearch"


def _entry(method, url, headers=None):
    msg = {"message": {"method": method, "params": {"requestId": "r1", "request": {"url": url, "method": "GET", "headers": headers or {}}}}}
    return {"message": json.dumps(msg)}


def test_find_request_takes_last_match():
    log = [_entry("Network.requestWillBeSent", "https://www.naukri.com/other"),
           _entry("Network.requestWillBeSent", API, {"AppId": "1", "x": "y"}),
           _entry("Network.responseReceived", API),
           _entry("Network.requestWillBeSent", API + "&z=1", {"AppId": "2"})]
    request = find_request(log, "/jobapi/v3/search")
    assert request["url"].endswith("&z=1") and request["headers"] == {"appid": "2"}
    assert request["method"] == "GET" and request["body"] is None and request["has_body"] is False
    assert find_request(log[:1], "/jobapi/v3/search") is None


def test_pick_headers_case_insensitive():
    assert pick_headers({"appid": "1", "cookie": "secret"}, ["AppId", " "]) == {"appid": "1"}


def test_with_page_replaces_page_and_keeps_encoding():
    url = with_page(API, 3)
    assert "pageNo=3" in url and "pageNo=1" not in url and "keyword=ai%20engineer" in url


def test_job_links():
    resp = {"jobDetails": [{"jdURL": "/job-listings-a-1"}, {"jdURL": "https://x.com/b"}, {}]}
    assert job_links(resp, "https://www.naukri.com/") == ["https://www.naukri.com/job-listings-a-1", "https://x.com/b"]
    assert job_links({"statusCode": 400}, "https://www.naukri.com") == []
