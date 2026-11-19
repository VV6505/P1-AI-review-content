from collections import Counter

from worker.m1.config import CrawlSettings
from worker.m1.crawl.discover import Frontier, classify, split_language
from worker.m1.crawl.errors import SkipReason


def test_phan_loai_page_type() -> None:
    assert classify("https://x.com/", root_host="x.com") == ("other", 1000)
    assert classify("https://x.com/pricing")[0] == "pricing"
    assert classify("https://x.com/features")[0] == "features"
    assert classify("https://x.com/docs")[0] == "docs"
    assert classify("https://x.com/changelog")[0] == "changelog"
    assert classify("https://x.com/compare")[0] == "compare"
    assert classify("https://x.com/faq")[0] == "faq"
    assert classify("https://x.com/about") == ("other", 0)
    # Host phụ: help center là faq
    assert classify("https://support.x.com/", root_host="x.com")[0] == "faq"


def test_trang_sau_va_slug_dai_bi_tru_diem() -> None:
    overview = classify("https://x.com/features")[1]
    deep = classify("https://x.com/features/a/b")[1]
    long_slug = classify("https://x.com/features/how-to-make-great-videos-fast")[1]
    assert overview > deep and overview > long_slug


def make_frontier(extra_ok: bool = False) -> Frontier:
    return Frontier(
        "x.com", lambda h: h == "x.com" or (extra_ok and h.endswith(".x.com")), CrawlSettings()
    )


def test_ly_do_bo_qua_luc_them_ung_vien() -> None:
    f = make_frontier()
    for url in [
        "https://other.com/pricing",
        "https://x.com/logo.png",
        "https://x.com/fr/pricing",
        "https://x.com/ja-jp/features",
        "https://x.com/login",
        "https://x.com/blog/some-long-post",
    ]:
        f.add(url, "sitemap")
    f.add("mailto:a@x.com", "link")
    f.add("javascript:void(0)", "link")
    reasons = {u: c.skip_reason for u, c in f.skipped.items()}
    assert reasons["https://other.com/pricing"] == SkipReason.OUT_OF_SCOPE
    assert reasons["https://x.com/logo.png"] == SkipReason.NON_HTML
    assert reasons["https://x.com/fr/pricing"] == SkipReason.LANGUAGE_NOT_ALLOWED
    assert reasons["https://x.com/ja-jp/features"] == SkipReason.LANGUAGE_NOT_ALLOWED
    assert reasons["https://x.com/login"] == SkipReason.EXCLUDED_PATH
    assert reasons["https://x.com/blog/some-long-post"] == SkipReason.EXCLUDED_PATH
    assert not f.candidates


def test_trung_url_sau_chuan_hoa_chi_giu_mot() -> None:
    f = make_frontier()
    f.add("https://x.com/pricing/", "sitemap")
    f.add("https://X.com/pricing?utm_source=a#top", "link:home", "Pricing")
    assert list(f.candidates) == ["https://x.com/pricing"]
    assert f.candidates["https://x.com/pricing"].text == "Pricing"  # bổ sung anchor text


def test_trang_chu_theo_path_van_duoc_crawl_dau_tien() -> None:
    f = make_frontier()
    f.add("https://x.com/products/copilot-for-teams", "home")
    cand = f.candidates["https://x.com/products/copilot-for-teams"]
    assert cand.score == 1000


# ---------------------------------------------------------------- ngôn ngữ (M1_CRAWL_LANGUAGES)
def lang_frontier(languages: tuple[str, ...] = ("en", "vi")) -> Frontier:
    return Frontier("x.com", lambda h: h == "x.com", CrawlSettings(languages=languages))


def test_tach_tien_to_ngon_ngu() -> None:
    assert split_language("https://x.com/vi/pricing") == ("vi", "https://x.com/pricing")
    assert split_language("https://x.com/en-US/docs/a") == ("en", "https://x.com/docs/a")
    assert split_language("https://x.com/vi") == ("vi", "https://x.com/")
    assert split_language("https://x.com/pricing") == (None, "https://x.com/pricing")
    assert split_language("https://x.com/") == (None, "https://x.com/")


def test_mac_dinh_en_vi_nhan_trang_tieng_viet_bo_ngon_ngu_khac() -> None:
    f = lang_frontier()
    for url in [
        "https://x.com/vi/features",
        "https://x.com/fr/pricing",
        "https://x.com/ja-jp/docs",
    ]:
        f.add(url, "sitemap")
    assert list(f.candidates) == ["https://x.com/vi/features"]
    assert f.skipped["https://x.com/fr/pricing"].skip_reason == SkipReason.LANGUAGE_NOT_ALLOWED
    assert f.skipped["https://x.com/ja-jp/docs"].skip_detail == "ja"


def test_cham_diem_tren_path_da_bo_tien_to() -> None:
    f = lang_frontier()
    f.add("https://x.com/vi/pricing", "sitemap")
    cand = f.candidates["https://x.com/vi/pricing"]
    assert (cand.page_type, cand.score) == classify("https://x.com/pricing")
    # Trang gốc của bản dịch không được điểm trang chủ
    f.add("https://x.com/vi", "sitemap")
    assert f.candidates["https://x.com/vi"].score == 0


def test_trang_goc_ban_dich_trung_trang_chu() -> None:
    f = lang_frontier()
    f.add("https://x.com/", "home")
    f.add("https://x.com/vi", "link:home")
    assert f.skipped["https://x.com/vi"].skip_reason == SkipReason.TRANSLATION_DUPLICATE


def test_ban_dich_trung_giu_ngon_ngu_uu_tien_hon() -> None:
    f = lang_frontier()  # en trước vi; path không tiền tố coi là en
    f.add("https://x.com/vi/pricing", "sitemap")
    f.add("https://x.com/pricing", "sitemap")  # ưu tiên hơn: thay chỗ bản vi chưa crawl
    f.add("https://x.com/en/pricing", "sitemap")  # cùng hạng với bản đang giữ: bỏ
    assert list(f.candidates) == ["https://x.com/pricing"]
    vi = f.skipped["https://x.com/vi/pricing"]
    assert vi.skip_reason == SkipReason.TRANSLATION_DUPLICATE
    assert vi.skip_detail == "https://x.com/pricing"
    assert f.skipped["https://x.com/en/pricing"].skip_reason == SkipReason.TRANSLATION_DUPLICATE


def test_doi_thu_tu_vi_en_thi_giu_ban_tieng_viet() -> None:
    f = lang_frontier(("vi", "en"))
    f.add("https://x.com/pricing", "sitemap")
    f.add("https://x.com/vi/pricing", "sitemap")
    assert list(f.candidates) == ["https://x.com/vi/pricing"]
    assert f.skipped["https://x.com/pricing"].skip_reason == SkipReason.TRANSLATION_DUPLICATE


def test_ban_da_crawl_thi_khong_bi_thay() -> None:
    f = lang_frontier(("vi", "en"))
    f.add("https://x.com/pricing", "sitemap")
    picked = f.pick_next(set(), Counter(), set())
    assert picked is not None and picked.url == "https://x.com/pricing"
    f.add("https://x.com/vi/pricing", "sitemap")  # ưu tiên hơn nhưng bản en đã crawl
    assert "https://x.com/pricing" in f.candidates
    vi = f.skipped["https://x.com/vi/pricing"]
    assert vi.skip_reason == SkipReason.TRANSLATION_DUPLICATE


def test_chi_vi_van_giu_trang_khong_tien_to() -> None:
    f = lang_frontier(("vi",))
    f.add("https://x.com/pricing", "sitemap")
    f.add("https://x.com/en/docs", "sitemap")
    assert "https://x.com/pricing" in f.candidates
    assert f.skipped["https://x.com/en/docs"].skip_reason == SkipReason.LANGUAGE_NOT_ALLOWED


def test_doc_m1_crawl_languages_tu_env() -> None:
    assert CrawlSettings().languages == ("en", "vi")
    assert CrawlSettings.from_env({"M1_CRAWL_LANGUAGES": "vi, EN"}).languages == ("vi", "en")
    assert CrawlSettings.from_env({"M1_CRAWL_LANGUAGES": '["en"]'}).languages == ("en",)
