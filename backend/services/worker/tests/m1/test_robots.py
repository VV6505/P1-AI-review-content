import asyncio

import pytest

from tests.m1.fakes import FakeClock, FakeHttp, fixture, text_response
from worker.m1.config import CrawlSettings
from worker.m1.crawl.http import HttpResponse
from worker.m1.crawl.robots import fetch_robots, parse_robots, robots_decision
from worker.m1.crawl.throttle import Throttle

SETTINGS = CrawlSettings()
ROBOTS_URL = "https://example.com/robots.txt"


def fetch(response: HttpResponse):
    clock = FakeClock()
    throttle = Throttle(1.0, clock=clock, sleep=clock.sleep)
    http = FakeHttp({ROBOTS_URL: response})
    robots = asyncio.run(fetch_robots("https://example.com", throttle, http, SETTINGS))
    return robots, throttle


def test_parse_dung_nhom_user_agent_va_sitemap() -> None:
    parsed = parse_robots(fixture("robots_allow.txt"), SETTINGS.ua_token)
    assert parsed.group == "own"  # có nhóm riêng cho UA của dự án thì không dùng nhóm *
    assert parsed.rules == [("disallow", "/secret")]
    assert parsed.sitemaps == ["https://example.com/sitemap.xml"]
    star = parse_robots(fixture("robots_allow.txt"), "khac")
    assert star.group == "*"
    assert star.crawl_delay == 2.0


def test_rule_khop_dai_nhat_thang_va_allow_thang_khi_bang_nhau() -> None:
    rules = parse_robots(fixture("robots_allow.txt"), "khac").rules
    assert robots_decision(rules, "https://example.com/pricing") == (True, "allow: /")
    assert robots_decision(rules, "https://example.com/private/x")[0] is False
    assert robots_decision(rules, "https://example.com/private/public-doc")[0] is True
    # Wildcard và $ theo RFC 9309
    assert robots_decision(rules, "https://example.com/a/b.pdf")[0] is False
    assert robots_decision(rules, "https://example.com/a/b.pdf?x=1")[0] is True
    assert robots_decision([("allow", "/a"), ("disallow", "/a")], "https://e.com/a")[0] is True


def test_2xx_doc_luat_va_dat_crawl_delay() -> None:
    body = "User-agent: *\nDisallow: /private/\nCrawl-delay: 2\n"
    robots, throttle = fetch(text_response(body))
    assert robots.policy == "parsed"
    assert robots.decide("https://example.com/private/x")[0] is False
    assert throttle._interval["example.com"] == 2.0  # Crawl-delay lớn hơn 1 giây thì theo robots


@pytest.mark.parametrize("status", [404, 410, 400, 401, 403])
def test_4xx_tru_429_coi_nhu_khong_co_robots(status: int) -> None:
    robots, _ = fetch(HttpResponse(status, b"", {}, "err"))
    assert robots.policy == "allow_all"
    assert robots.decide("https://example.com/any")[0] is True


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_5xx_va_429_coi_nhu_cam_toan_bo(status: int) -> None:
    robots, _ = fetch(HttpResponse(status, b"", {}, "err"))
    assert robots.policy == "unavailable"
    assert robots.decide("https://example.com/")[0] is False


def test_timeout_coi_nhu_cam_toan_bo() -> None:
    robots, _ = fetch(HttpResponse(None, b"", {}, "TimeoutError", timed_out=True))
    assert robots.policy == "unavailable"
    assert robots.timed_out is True
    assert robots.decide("https://example.com/")[0] is False


def test_trang_thu_thach_waf_khong_phai_robots() -> None:
    body = fixture("cloudflare_challenge.html").encode()
    robots, _ = fetch(HttpResponse(403, body, {"cf-mitigated": "challenge"}, "403"))
    assert robots.policy == "waf_challenge"
    assert robots.decide("https://example.com/")[0] is False
    # 403 thường (không có dấu hiệu challenge) vẫn là "không có robots"
    plain, _ = fetch(HttpResponse(403, b"Forbidden", {}, "403"))
    assert plain.policy == "allow_all"
