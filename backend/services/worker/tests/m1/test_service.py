"""Test `crawl_product` end-to-end với fake fetcher / HTTP (không mạng, không trình duyệt)."""

from __future__ import annotations

import pytest

from tests.m1.fakes import (
    FakeFetcher,
    FakeHttp,
    MemoryStore,
    challenge_page,
    fixture,
    page,
    run_crawl,
    text_response,
)
from worker.m1.config import CrawlOptions, CrawlSettings
from worker.m1.crawl.errors import CrawlErrorCode, SkipReason
from worker.m1.crawl.fetcher import FetchResult
from worker.m1.crawl.http import HttpResponse

ROOT = "https://example.com"
HOME = "https://example.com/"


def site(paths: list[str], host: str = ROOT, **home_kwargs: object) -> dict[str, FetchResult]:
    """Trang chủ có link tới mọi path; mỗi path là một trang bình thường."""
    pages = {HOME: page(HOME, [host + p for p in paths], **home_kwargs)}
    for p in paths:
        pages[host + p] = page(host + p)
    return pages


def reasons(result) -> dict[str, SkipReason]:  # noqa: ANN001
    return {s.url: s.reason for s in result.skipped}


# ---------------------------------------------------------------- luồng chính
def test_crawl_thanh_cong_tra_du_truong_sources() -> None:
    result, fetcher, store, _ = run_crawl(ROOT, site(["/pricing", "/features", "/docs"]))

    assert result.status == "completed"
    assert result.error_code is None and result.retryable is None and not result.partial
    assert [p.url for p in result.pages] == [
        HOME,
        f"{ROOT}/pricing",
        f"{ROOT}/features",
        f"{ROOT}/docs",
    ]
    assert [p.page_type for p in result.pages] == ["other", "pricing", "features", "docs"]
    first = result.pages[0]
    assert first.source_id == "src_01" and result.pages[3].source_id == "src_04"
    assert first.content_hash == first.raw_hash and first.content_hash.startswith("sha256:")
    assert first.region == "VN" and first.locale == "en-US" and first.fetched_at
    assert first.raw_path == "pages/src_01.raw.md" and first.fit_path == "pages/src_01.md"
    assert first.found_via == "home" and not first.unchanged
    assert set(store.saved) == {p.url for p in result.pages}
    assert result.pages_used == 4 and result.pages_found == 4
    assert result.robots["example.com"].policy == "parsed"
    assert fetcher.calls[0] == HOME  # trang chủ luôn crawl đầu tiên


def test_luu_title_va_og_site_name_de_extract_tim_ten() -> None:
    pages = site(["/pricing"], title="Acme | Home\n-->", site_name="Acme")
    result, _, store, _ = run_crawl(ROOT, pages)
    home = result.pages[0]
    assert home.title == "Acme Home" and home.site_name == "Acme"  # đã làm sạch cho header
    assert store.saved[HOME]["title"] == "Acme | Home\n-->"  # store tự làm sạch khi ghi
    assert store.saved[HOME]["site_name"] == "Acme"


def test_khoang_cach_request_cung_host_it_nhat_1_giay() -> None:
    result, _, _, _ = run_crawl(ROOT, site(["/pricing", "/features", "/docs", "/faq"]))
    gap = result.min_observed_interval_s["example.com"]
    assert gap is not None and gap >= 1.0
    kinds = {r.kind for r in result.requests}
    assert kinds == {"robots", "sitemap", "page"}  # robots và sitemap cũng bị throttle


def test_sitemap_bo_sung_ung_vien() -> None:
    http = FakeHttp(
        {
            f"{ROOT}/sitemap.xml": text_response(
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>{ROOT}/pricing</loc></url><url><loc>{ROOT}/changelog</loc></url></urlset>"
            )
        }
    )
    pages = {
        HOME: page(HOME),
        f"{ROOT}/pricing": page(f"{ROOT}/pricing"),
        f"{ROOT}/changelog": page(f"{ROOT}/changelog"),
    }
    result, _, _, _ = run_crawl(ROOT, pages, http=http)
    assert [p.page_type for p in result.pages] == ["other", "pricing", "changelog"]
    assert result.pages[1].found_via == "sitemap"


# ---------------------------------------------------------------- hạn mức
def test_quota_theo_page_type_truoc_roi_lap_theo_diem() -> None:
    paths = [f"/pricing-{i}" for i in range(12)] + [f"/features-{i}" for i in range(15)]
    result, _, _, _ = run_crawl(ROOT, site(paths))
    first = [p.page_type for p in result.pages[1:15]]  # sau trang chủ
    assert first.count("pricing") == 4 and first.count("features") == 10
    # Hết ứng viên trong hạn mức thì lấp tiếp theo điểm: pricing (điểm cao hơn) trước
    assert result.pages[15].page_type == "pricing"


def test_toi_da_30_trang_va_phan_con_lai_la_over_limit() -> None:
    paths = [f"/features-{i}" for i in range(60)]
    result, fetcher, _, _ = run_crawl(ROOT, site(paths))
    assert len(result.pages) == 30 and len(fetcher.calls) == 30
    assert result.skipped_counts[SkipReason.OVER_LIMIT.value] == 31
    assert result.pages_found == 61


def test_toi_da_5_trang_host_phu_va_tinh_vao_30() -> None:
    support = "https://support.example.com"
    pages = site([f"/features-{i}" for i in range(8)])
    faq_paths = [f"/faq-{i}" for i in range(10)]
    for p in faq_paths:
        pages[support + p] = page(support + p)
    pages[HOME] = page(
        HOME, [f"{support}{p}" for p in faq_paths] + [f"{ROOT}/features-{i}" for i in range(8)]
    )

    result, _, _, _ = run_crawl(ROOT, pages, options=CrawlOptions(allow_subdomains=True))
    extra = [p for p in result.pages if "support.example.com" in p.url]
    assert len(extra) == 5
    assert all(p.page_type == "faq" for p in extra)
    assert result.skipped_counts[SkipReason.OVER_LIMIT.value] == 5

    # Gộp chung với giới hạn 30: host phụ không làm vượt 30 trang
    many = site([f"/features-{i}" for i in range(40)])
    for p in faq_paths:
        many[support + p] = page(support + p)
    many[HOME] = page(
        HOME, [f"{support}{p}" for p in faq_paths] + [f"{ROOT}/features-{i}" for i in range(40)]
    )
    big, _, _, _ = run_crawl(ROOT, many, options=CrawlOptions(allow_subdomains=True))
    assert len(big.pages) == 30


def test_host_phu_khong_duoc_crawl_khi_chua_bat() -> None:
    support = "https://support.example.com/faq"
    pages = site(["/features"])
    pages[HOME] = page(HOME, [support, f"{ROOT}/features"])
    pages[support] = page(support)
    result, fetcher, _, http = run_crawl(ROOT, pages)
    assert support not in fetcher.calls
    assert result.skipped_counts[SkipReason.OUT_OF_SCOPE.value] == 1
    assert not any(
        "support.example.com" in c for c in http.calls
    )  # cũng không tải robots của host đó


def test_bo_qua_trang_ngon_ngu_khong_cho_phep_va_file_khong_phai_html() -> None:
    pages = site(["/pricing"])
    pages[HOME] = page(
        HOME,
        [f"{ROOT}/pricing", f"{ROOT}/fr/pricing", f"{ROOT}/ja-jp/features", f"{ROOT}/logo.png"],
    )
    result, fetcher, _, _ = run_crawl(ROOT, pages)
    assert result.skipped_counts[SkipReason.LANGUAGE_NOT_ALLOWED.value] == 2
    assert result.skipped_counts[SkipReason.NON_HTML.value] == 1
    assert fetcher.calls == [HOME, f"{ROOT}/pricing"]


def test_trang_trung_noi_dung_bi_bo_qua() -> None:
    same = fixture("page.md")
    pages = site(["/features", "/product"])
    pages[f"{ROOT}/features"] = page(f"{ROOT}/features", body=same)
    pages[f"{ROOT}/product"] = page(f"{ROOT}/product", body=same)
    result, _, _, _ = run_crawl(ROOT, pages)
    assert len(result.pages) == 2
    assert result.skipped_counts[SkipReason.DUPLICATE.value] == 1
    assert SkipReason.DUPLICATE in reasons(result).values()


# ---------------------------------------------------------------- NFR-04 unchanged
def test_trang_khong_doi_khong_ghi_lai_nhung_van_nam_trong_ket_qua() -> None:
    pages = site(["/pricing", "/features"])
    first, _, _, _ = run_crawl(ROOT, pages)
    previous = {p.url: p.content_hash for p in first.pages if p.url != f"{ROOT}/features"}
    # features đổi nội dung
    pages[f"{ROOT}/features"] = page(
        f"{ROOT}/features", body=fixture("page.md") + "\nNew feature!\n"
    )

    result, _, store, _ = run_crawl(ROOT, pages, previous_hashes=previous)
    by_url = {p.url: p for p in result.pages}
    assert len(result.pages) == 3  # vẫn đủ 3 trang để PKB giữ nguồn
    assert by_url[HOME].unchanged and by_url[f"{ROOT}/pricing"].unchanged
    assert by_url[HOME].raw_path is None and by_url[HOME].fit_path is None
    assert not by_url[f"{ROOT}/features"].unchanged
    assert set(store.saved) == {f"{ROOT}/features"}  # chỉ trang đổi mới được ghi
    assert result.skipped_counts[SkipReason.UNCHANGED.value] == 2
    assert result.status == "completed"


# ---------------------------------------------------------------- lỗi cấp job
def test_url_sai_la_invalid_url_khong_gui_request() -> None:
    result, fetcher, _, http = run_crawl("ftp://example.com", {}, robots=None)
    assert result.status == "failed" and result.error_code == CrawlErrorCode.INVALID_URL
    assert result.retryable is False
    assert result.error_message.startswith("invalid_url")
    assert fetcher.calls == [] and http.calls == []


@pytest.mark.parametrize(
    ("robots", "code", "retryable"),
    [
        (HttpResponse(500, b"", {}, "500"), CrawlErrorCode.ROBOTS_UNAVAILABLE, True),
        (HttpResponse(503, b"", {}, "503"), CrawlErrorCode.ROBOTS_UNAVAILABLE, True),
        (HttpResponse(429, b"", {}, "429"), CrawlErrorCode.ROBOTS_UNAVAILABLE, True),
        (
            HttpResponse(None, b"", {}, "timeout", timed_out=True),
            CrawlErrorCode.ROBOTS_UNAVAILABLE,
            True,
        ),
        (HttpResponse(None, b"", {}, "gaierror"), CrawlErrorCode.HOME_UNREACHABLE, True),
        (text_response(fixture("robots_disallow_all.txt")), CrawlErrorCode.ROBOTS_DISALLOW, False),
        (
            HttpResponse(
                403, fixture("cloudflare_challenge.html").encode(), {"cf-mitigated": "challenge"}
            ),
            CrawlErrorCode.WAF_CHALLENGE,
            False,
        ),
    ],
)
def test_robots_cua_trang_chu_quyet_dinh_job(
    robots: HttpResponse, code: CrawlErrorCode, retryable: bool
) -> None:
    http = FakeHttp({f"{ROOT}/robots.txt": robots})
    result, fetcher, _, _ = run_crawl(ROOT, site(["/pricing"]), http=http, robots=None)
    assert result.status == "failed" and result.error_code == code
    assert result.retryable is retryable
    assert result.error_message.startswith(code.value)
    assert fetcher.calls == []  # không mở trang nào
    assert result.pages == []


@pytest.mark.parametrize("status", [404, 401, 403])
def test_robots_4xx_tru_429_van_duoc_crawl(status: int) -> None:
    http = FakeHttp({f"{ROOT}/robots.txt": HttpResponse(status, b"", {}, str(status))})
    result, _, _, _ = run_crawl(ROOT, site(["/pricing"]), http=http, robots=None)
    assert result.status == "completed"
    assert result.robots["example.com"].policy == "allow_all"


def test_robots_cam_trang_con_thi_bo_qua_trang_do() -> None:
    robots = "User-agent: *\nDisallow: /docs\n"
    result, fetcher, _, _ = run_crawl(ROOT, site(["/pricing", "/docs"]), robots=robots)
    assert result.status == "completed"
    assert f"{ROOT}/docs" not in fetcher.calls
    assert reasons(result)[f"{ROOT}/docs"] == SkipReason.ROBOTS_DISALLOWED


@pytest.mark.parametrize(
    ("home", "code", "retryable"),
    [
        (challenge_page(HOME, 403), CrawlErrorCode.WAF_CHALLENGE, False),
        (
            FetchResult(url=HOME, status_code=429, raw_markdown="x" * 500),
            CrawlErrorCode.WAF_CHALLENGE,
            False,
        ),
        (
            page(HOME, body="Just a moment... verify you are human"),
            CrawlErrorCode.WAF_CHALLENGE,
            False,
        ),
        (
            page(HOME, redirected_url="https://example.com/login?next=/"),
            CrawlErrorCode.LOGIN_REDIRECT,
            False,
        ),
        (page(HOME, body="Hi"), CrawlErrorCode.NO_CONTENT, False),
        (
            FetchResult(url=HOME, status_code=404, raw_markdown="x" * 500),
            CrawlErrorCode.INVALID_URL,
            False,
        ),
        (
            FetchResult(url=HOME, status_code=410, raw_markdown="x" * 500),
            CrawlErrorCode.INVALID_URL,
            False,
        ),
        (
            FetchResult(url=HOME, status_code=503, raw_markdown="x" * 500),
            CrawlErrorCode.HOME_UNREACHABLE,
            True,
        ),
        (
            FetchResult(url=HOME, success=False, error_message="net::ERR_NAME_NOT_RESOLVED"),
            CrawlErrorCode.HOME_UNREACHABLE,
            True,
        ),
    ],
)
def test_trang_chu_loi_thi_job_failed_va_dung_ngay(
    home: FetchResult, code: CrawlErrorCode, retryable: bool
) -> None:
    pages = {HOME: home, f"{ROOT}/pricing": page(f"{ROOT}/pricing")}
    result, fetcher, _, _ = run_crawl(ROOT, pages)
    assert result.status == "failed" and result.error_code == code and result.retryable is retryable
    assert fetcher.calls == [HOME]  # không thử lại, không mở thêm trang nào
    assert result.pages == []


def test_trinh_duyet_sap_o_trang_chu_la_home_unreachable() -> None:
    fetcher = FakeFetcher({}, fail=[HOME])
    result, _, _, _ = run_crawl(ROOT, {}, fetcher=fetcher)
    assert result.error_code == CrawlErrorCode.HOME_UNREACHABLE and result.retryable is True


def test_trang_con_chuyen_huong_toi_dang_nhap_thi_bo_qua_va_crawl_tiep() -> None:
    pages = site(["/pricing", "/app"])
    pages[f"{ROOT}/app"] = page(f"{ROOT}/app", redirected_url="https://example.com/login")
    result, fetcher, _, _ = run_crawl(ROOT, pages)
    assert result.status == "completed"
    assert reasons(result)[f"{ROOT}/app"] == SkipReason.LOGIN_REDIRECT
    assert f"{ROOT}/pricing" in fetcher.calls
    assert [p.url for p in result.pages] == [HOME, f"{ROOT}/pricing"]


def test_loi_trang_con_khong_lam_hong_job() -> None:
    fetcher = FakeFetcher(site(["/pricing", "/features"]), fail=[f"{ROOT}/pricing"])
    result, _, _, _ = run_crawl(ROOT, {}, fetcher=fetcher)
    assert result.status == "completed"
    assert reasons(result)[f"{ROOT}/pricing"] == SkipReason.FETCH_ERROR
    assert len(result.pages) == 2


def test_trang_con_404_la_fetch_error() -> None:
    pages = site(["/pricing", "/features"])
    del pages[f"{ROOT}/pricing"]  # FakeFetcher trả 404
    result, _, _, _ = run_crawl(ROOT, pages)
    assert reasons(result)[f"{ROOT}/pricing"] == SkipReason.FETCH_ERROR
    assert result.status == "completed"


# ---------------------------------------------------------------- bị chặn giữa chừng
def test_bi_chan_o_trang_con_thi_dung_ngay_va_van_completed_neu_du_trang() -> None:
    pages = site(["/pricing", "/features", "/docs"])
    pages[f"{ROOT}/features"] = challenge_page(f"{ROOT}/features", 403)
    result, fetcher, _, _ = run_crawl(ROOT, pages)

    assert result.status == "completed"
    assert result.partial is True
    assert result.warning == "blocked_mid_crawl:http_403"
    assert [p.url for p in result.pages] == [HOME, f"{ROOT}/pricing"]
    assert f"{ROOT}/docs" not in fetcher.calls  # không gửi thêm request tới host đó
    r = reasons(result)
    assert r[f"{ROOT}/features"] == SkipReason.BLOCKED
    assert r[f"{ROOT}/docs"] == SkipReason.BLOCKED  # trang chưa crawl cũng ghi "blocked"


def test_bi_chan_o_trang_con_khi_chi_co_trang_chu_thi_failed_waf_challenge() -> None:
    pages = site(["/pricing"])
    pages[f"{ROOT}/pricing"] = FetchResult(
        url=f"{ROOT}/pricing", status_code=429, raw_markdown="x" * 500
    )
    result, _, _, _ = run_crawl(ROOT, pages)
    assert result.status == "failed"
    assert result.error_code == CrawlErrorCode.WAF_CHALLENGE and result.retryable is False
    assert result.error_message.startswith("waf_challenge")
    assert result.partial is False and result.warning is None


def test_host_phu_bi_chan_thi_chi_dung_host_do() -> None:
    support = "https://support.example.com"
    pages = site(["/features", "/docs"])
    pages[HOME] = page(
        HOME, [f"{support}/faq", f"{support}/help", f"{ROOT}/features", f"{ROOT}/docs"]
    )
    pages[f"{support}/faq"] = challenge_page(f"{support}/faq", 403)
    pages[f"{support}/help"] = page(f"{support}/help")
    result, fetcher, _, _ = run_crawl(ROOT, pages, options=CrawlOptions(allow_subdomains=True))

    assert result.status == "completed" and result.partial is True
    assert f"{support}/help" not in fetcher.calls  # host đã bị chặn: không gửi thêm
    assert f"{ROOT}/docs" in fetcher.calls  # host gốc chạy tiếp
    assert reasons(result)[f"{support}/help"] == SkipReason.BLOCKED


# ---------------------------------------------------------------- cấu hình
def test_cau_hinh_mac_dinh_bang_spike_va_doc_duoc_tu_env() -> None:
    s = CrawlSettings()
    assert (s.max_pages, s.max_extra_host_pages, s.min_interval_s) == (30, 5, 1.0)
    assert s.type_quota["pricing"] == 4 and s.extra_host_types == ("faq", "pricing")
    assert s.ua_token == "aireviewcontentfactory"
    env = {"M1_CRAWL_MAX_PAGES": "5", "M1_CRAWL_TYPE_QUOTA": '{"pricing": 1}', "OTHER": "x"}
    custom = CrawlSettings.from_env(env)
    assert custom.max_pages == 5 and custom.type_quota == {"pricing": 1}
    assert custom.min_interval_s == 1.0


def test_ma_loi_retryable() -> None:
    retryable = {c for c in CrawlErrorCode if c.retryable}
    assert retryable == {CrawlErrorCode.ROBOTS_UNAVAILABLE, CrawlErrorCode.HOME_UNREACHABLE}


def test_store_va_http_duoc_inject() -> None:
    store = MemoryStore()
    result, _, used_store, _ = run_crawl(ROOT, site(["/pricing"]), store=store)
    assert used_store is store and result.status == "completed"
