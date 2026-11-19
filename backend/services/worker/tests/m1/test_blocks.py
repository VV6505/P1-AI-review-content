from tests.m1.fakes import challenge_page, fixture, page
from worker.m1.crawl.blocks import detect_block, waf_challenge_response
from worker.m1.crawl.fetcher import FetchResult
from worker.m1.crawl.http import HttpResponse


def test_phat_hien_waf_qua_header_cf_mitigated() -> None:
    resp = HttpResponse(403, b"", {"cf-mitigated": "challenge", "cf-ray": "abc"})
    assert "cf-ray=abc" in waf_challenge_response(resp)


def test_phat_hien_waf_qua_marker_trong_html() -> None:
    resp = HttpResponse(403, fixture("cloudflare_challenge.html").encode(), {})
    assert waf_challenge_response(resp)


def test_response_binh_thuong_khong_phai_waf() -> None:
    assert waf_challenge_response(HttpResponse(200, b"User-agent: *\nAllow: /", {})) == ""
    # Chữ "captcha" trong CSS của form thường không đủ để coi là challenge
    assert waf_challenge_response(HttpResponse(200, b".captcha{display:none}", {})) == ""


def test_trang_thu_thach_la_bot_challenge() -> None:
    block = detect_block(challenge_page("https://x.com/"), is_home=True, min_home_chars=200)
    assert block is not None and block.is_waf


def test_http_403_va_429_la_waf_con_401_503_thi_khong() -> None:
    def is_waf(status: int) -> bool:
        result = FetchResult(url="https://x.com/", status_code=status, raw_markdown="x" * 500)
        block = detect_block(result, is_home=False, min_home_chars=200)
        assert block is not None
        return block.is_waf

    assert is_waf(403) and is_waf(429)
    assert not is_waf(503) and not is_waf(401)


def test_crawl4ai_bao_loi_anti_bot_thi_la_waf() -> None:
    result = FetchResult(
        url="https://x.com/", success=False, error_message="Blocked by anti-bot protection"
    )
    block = detect_block(result, is_home=True, min_home_chars=200)
    assert block is not None and block.is_waf


def test_loi_chromium_blocked_khong_bi_nham_voi_waf() -> None:
    for message in ("net::ERR_BLOCKED_BY_RESPONSE", "net::ERR_BLOCKED_BY_CLIENT"):
        result = FetchResult(url="https://x.com/", success=False, error_message=message)
        block = detect_block(result, is_home=True, min_home_chars=200)
        assert block is not None and block.kind == "crawl_failed" and not block.is_waf


def test_loi_mang_khong_phai_waf() -> None:
    result = FetchResult(
        url="https://x.com/", success=False, error_message="net::ERR_NAME_NOT_RESOLVED"
    )
    block = detect_block(result, is_home=True, min_home_chars=200)
    assert block is not None and block.kind == "crawl_failed" and not block.is_waf


def test_404_duoc_kiem_truoc_anti_bot() -> None:
    result = FetchResult(
        url="https://x.com/a", status_code=404, success=False, error_message="blocked"
    )
    block = detect_block(result, is_home=False, min_home_chars=200)
    assert block is not None and block.kind == "not_found"


def test_chuyen_huong_toi_dang_nhap() -> None:
    result = page("https://x.com/app", redirected_url="https://x.com/login?next=/app")
    block = detect_block(result, is_home=False, min_home_chars=200)
    assert block is not None and block.kind == "login_redirect"


def test_trang_chu_qua_ngan() -> None:
    result = page("https://x.com/", body="Hi")
    block = detect_block(result, is_home=True, min_home_chars=200)
    assert block is not None and block.kind == "too_short"
    assert (
        detect_block(result, is_home=False, min_home_chars=200) is None
    )  # trang con ngắn thì được
