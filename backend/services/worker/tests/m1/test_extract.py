"""Test `extract_product` với crawl giả và LLM fixture. Dữ liệu là sản phẩm giả, không gọi mạng."""

from __future__ import annotations

import asyncio
import copy
import json
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from worker.m1.crawl.store import LocalPageStore
from worker.m1.extract import ExtractError, ExtractErrorCode, ExtractResult, extract_product
from worker.m1.extract.evidence import has_word, norm, numbers_in, price_in_evidence
from worker.m1.extract.pages import parse_header
from worker.m1.extract.schema import PKBExtract
from worker.m1.extract.service import ExtractSettings
from worker.m1.llm import LLM, CostBreakdown, LLMErrorCode, LLMSettings
from worker.m1.llm.fixture import FixtureTransport
from worker.m1.models import CrawlResult, PageRecord
from worker.m1.pkb.validate import validate_pkb

FIXTURES = Path(__file__).parent / "fixtures" / "llm"
NOW = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)

HOME_MD = """<!-- source_id: src_01 | url: https://acme.example/ -->

# Acme PDF
Acme PDF is a free online PDF toolkit with **90+ tools**.
![logo](https://acme.example/logo.png)
[Pricing](https://acme.example/pricing)
"""
PRICING_RAW = """# Pricing
Free $0 forever. Pro $9 per month, billed monthly.
Pro $90 per year, billed yearly.
"""
FEATURES_MD = """# Features
Merge PDF: combine many files into one.
Acme PDF offers 100+ tools for every task.
Công cụ nén PDF giúp giảm dung lượng tệp.
"""
PAGES = {
    "pages/src_01-other-home.md": HOME_MD,
    "pages/src_01-other-home.raw.md": HOME_MD,
    "pages/src_02-pricing-pricing.md": "# Pricing\n(fit làm rơi giá)",
    "pages/src_02-pricing-pricing.raw.md": PRICING_RAW,
    "pages/src_03-features-features.md": FEATURES_MD,
    "pages/src_03-features-features.raw.md": FEATURES_MD,
}


class MemoryReader:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def read_page(self, path: str) -> str:
        if path not in self.pages:
            raise FileNotFoundError(path)  # như LocalPageStore
        return self.pages[path]


def record(sid: str, page_type: str, slug: str, score: int, **kw: Any) -> PageRecord:
    name = f"pages/{sid}-{page_type}-{slug}"
    base: dict[str, Any] = {
        "source_id": sid,
        "url": f"https://acme.example/{'' if slug == 'home' else slug}",
        "page_type": page_type,
        "content_hash": f"sha256:{sid}raw",
        "fetched_at": "2026-10-21T01:00:00+00:00",
        "region": "VN",
        "locale": "en-US",
        "raw_path": f"{name}.raw.md",
        "fit_path": f"{name}.md",
        "raw_hash": f"sha256:{sid}raw",
        "fit_hash": f"sha256:{sid}fit",
        "final_url": "https://acme.example/",
        "score": score,
        "found_via": "home",
    }
    return PageRecord(**{**base, **kw})


def crawl(pages: list[PageRecord] | None = None, status: str = "completed") -> CrawlResult:
    return CrawlResult.model_validate(
        {
            "status": status,
            "root_url": "https://acme.example/",
            "pages": pages
            if pages is not None
            else [
                record("src_01", "other", "home", 1000),
                record("src_02", "pricing", "pricing", 100),
                record("src_03", "features", "features", 80),
            ],
            "started_at": "2026-10-21T01:00:00+00:00",
            "finished_at": "2026-10-21T01:01:00+00:00",
        }
    )


def fact(sid: str, evidence: str, **kw: Any) -> dict[str, Any]:
    return {"origin": "crawled", "source_id": sid, "evidence": evidence, **kw}


GOOD: dict[str, Any] = {
    "identity": {
        "name": fact("src_01", "Acme PDF", value="Acme PDF"),
        "description": fact(
            "src_01",
            "Acme PDF is a free online PDF toolkit with 90+ tools.",
            value="Free online PDF toolkit with 90+ tools.",
        ),
        "models": [],
    },
    "pricing": {
        "plans": [
            fact(
                "src_02",
                "Free $0 forever.",
                name="Free",
                currency="USD",
                list_price=0,
                price_unit="month",
                billing_cycle="monthly",
                price_text="$0 forever",
            ),
            fact(
                "src_02",
                "Pro $9 per month, billed monthly.",
                name="Pro",
                currency="USD",
                list_price=9,
                price_unit="month",
                billing_cycle="monthly",
                price_text="$9 per month",
            ),
            fact(
                "src_02",
                "Pro $90 per year, billed yearly.",
                name="Pro",
                currency="USD",
                list_price=90,
                price_unit="year",
                billing_cycle="yearly",
                price_text="$90 per year",
            ),
        ],  # fmt: skip
        "usage_prices": [],
        "other_views": [],
    },
    "features": [
        fact("src_03", "Merge PDF: combine many files into one.", name="Merge PDF"),
        fact("src_03", "Công cụ nén PDF giúp giảm dung lượng tệp.", name="Nén PDF"),
    ],
    "use_cases": [],
    "limitations": [],
    "conflicts": [
        {
            "field": "identity.description",
            "topic": "số lượng công cụ",
            "claims": [
                {"value": "90+ tools", "source_id": "src_01", "evidence": "with 90+ tools"},
                {"value": "100+ tools", "source_id": "src_03", "evidence": "offers 100+ tools"},
            ],
        }
    ],
}
USAGE = {"prompt_token_count": 3000, "candidates_token_count": 800}


def ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "usage_metadata": USAGE, "finish_reason": "STOP"}


def run(
    responses: list[dict[str, Any]],
    crawl_result: CrawlResult | None = None,
    pages: dict[str, str] | None = None,
    settings: ExtractSettings | None = None,
) -> tuple[ExtractResult | ExtractError, FixtureTransport]:
    transport = FixtureTransport(responses)

    async def no_sleep(_: float) -> None:
        return None

    llm = LLM(transport, LLMSettings(provider="fixture"), sleep=no_sleep, now=lambda: NOW)

    async def call() -> ExtractResult | ExtractError:
        try:
            return await extract_product(
                crawl_result or crawl(), MemoryReader(pages or PAGES), llm, settings=settings
            )
        except ExtractError as e:
            return e

    return asyncio.run(call()), transport


def good() -> dict[str, Any]:
    return copy.deepcopy(GOOD)


# ---------------------------------------------------------------- luồng chính
def test_tra_pkb_v03_software_hop_le() -> None:
    res, transport = run([ok(good())])
    assert isinstance(res, ExtractResult)
    data = res.data
    assert data["schema_version"] == "0.3"
    assert data["identity"]["product_kind"] == "software"
    assert data["identity"]["website"] == "https://acme.example/"
    assert data["pricing"]["region"] == "VN" and data["pricing"]["locale"] == "en-US"
    assert [f["id"] for f in data["features"]] == ["f1", "f2"]
    validate_pkb(data, res.sources)
    # 1 lời gọi, gom mọi trang; pricing gửi raw, trang khác gửi fit
    [call] = transport.calls
    assert "SOURCE src_01" in call["prompt"] and "SOURCE src_03" in call["prompt"]
    assert "Pro $9 per month" in call["prompt"]  # raw của pricing
    assert "logo.png" not in call["prompt"]  # đã bỏ ảnh và URL link
    variants = {s["id"]: (s["variant"], s["content_hash"]) for s in res.sources}
    assert variants["src_02"] == ("raw", "sha256:src_02raw")
    assert variants["src_03"] == ("fit", "sha256:src_03fit")
    # chi phí: 1 item exact
    CostBreakdown.model_validate(res.cost_breakdown)
    [item] = res.cost_breakdown["items"]
    assert item["step"] == "extract" and item["cost_status"] == "exact"
    assert res.evidence_in_source == 1.0


def test_chon_top_k_theo_diem() -> None:
    pages = [record(f"src_{i:02d}", "features", f"f{i}", 100 - i) for i in range(1, 13)]
    texts = {p.fit_path: f"page {p.source_id}" for p in pages if p.fit_path}
    data = good()
    data["pricing"]["plans"] = []
    data["features"] = []
    data["conflicts"] = []
    data["identity"] = {"name": fact("src_01", "page src_01", value="Acme")}
    res, transport = run([ok(data)], crawl(pages), texts)
    assert isinstance(res, ExtractResult)
    assert [s["id"] for s in res.sources] == [f"src_{i:02d}" for i in range(1, 11)]
    assert "src_11" not in transport.calls[0]["prompt"]


def test_trang_unchanged_khong_co_markdown_bi_bo_kem_warning() -> None:
    pages = [
        record("src_01", "other", "home", 1000),
        record("src_02", "pricing", "pricing", 100),
        record("src_03", "features", "features", 80, raw_path=None, fit_path=None),
    ]
    data = good()
    data["features"] = []
    data["conflicts"] = []
    res, _ = run([ok(data)], crawl(pages))
    assert isinstance(res, ExtractResult)
    assert "page_not_stored:src_03" in res.warnings
    assert [s["id"] for s in res.sources] == ["src_01", "src_02"]


# ---------------------------------------------------------------- evidence
def test_evidence_khong_co_trong_nguon_giu_fact_va_canh_bao() -> None:
    data = good()
    data["features"][0]["evidence"] = "Merge PDF: the best merger in the world."
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert res.data["features"][0]["name"] == "Merge PDF"  # vẫn giữ fact
    assert "evidence_not_found:features[0]" in res.warnings
    assert res.evidence_in_source < 1.0


def test_fact_tro_toi_trang_khong_gui_bi_loai() -> None:
    data = good()
    data["features"].append(fact("src_99", "Split PDF", name="Split PDF"))
    data["identity"]["description"]["source_id"] = "src_42"
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert [f["name"] for f in res.data["features"]] == ["Merge PDF", "Nén PDF"]
    assert res.data["identity"].get("description") is None
    assert "unknown_source_id:features[2]:src_99" in res.warnings
    assert "unknown_source_id:identity.description:src_42" in res.warnings
    validate_pkb(res.data, res.sources)


def test_evidence_qua_dai_bi_cat_tai_ranh_gioi_tu() -> None:
    data = good()
    data["features"][0]["evidence"] = "Merge PDF: combine many files into one. " * 8
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert len(res.data["features"][0]["evidence"]) <= 200
    assert "evidence_truncated:1" in res.warnings


def test_so_khop_tieng_viet_nfd_va_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "Công cụ nén PDF")
    assert nfd != "Công cụ nén PDF"
    assert norm(nfd) == norm("Công cụ nén PDF")
    data = good()
    data["features"][1]["evidence"] = nfd
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert not [w for w in res.warnings if w.startswith("evidence_not_found")]


def test_gia_khuyen_mai_cao_hon_gia_niem_yet_thi_canh_bao_khong_tu_dao() -> None:
    # Ca thật ElevenLabs 21/10: "$22 First month 50% off $11" → LLM ghi list 11, promo 22
    data = good()
    data["pricing"]["plans"][1].update(list_price=4.5, promo_price=9, promo_terms="tháng đầu")
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert "promo_above_list:pricing.plans[1]" in res.warnings
    assert res.data["pricing"]["plans"][1]["list_price"] == 4.5


def test_ten_san_pham_khong_co_trong_evidence_thi_canh_bao() -> None:
    # Ca thật PDFCraft 21/10: name "PDFCraft", evidence là tagline có trong trang, không có tên
    data = good()
    data["identity"]["name"] = fact("src_01", "free online PDF toolkit", value="PDFCraft")
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert res.data["identity"]["name"]["value"] == "PDFCraft"  # vẫn giữ fact
    assert "value_not_in_evidence:identity.name" in res.warnings
    assert not [w for w in res.warnings if w.startswith("evidence_not_found")]


def test_ten_plan_va_gia_khong_co_trong_evidence_thi_canh_bao() -> None:
    data = good()
    data["pricing"]["plans"][1].update(name="Plus", list_price=19)
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert "value_not_in_evidence:pricing.plans[1].name" in res.warnings
    assert "value_not_in_evidence:pricing.plans[1].list_price" in res.warnings
    # Free $0 và Pro $90 khớp evidence
    assert len([w for w in res.warnings if w.startswith("value_not_in_evidence")]) == 2


CREATOR_MD = "# Pricing\nCreator\n$22 First month 50% off\n$11per month\n"


@pytest.mark.parametrize(("list_price", "promo_price"), [(22, 11), (11, 22)])
def test_gia_creator_22_11_khop_evidence_ca_khi_bi_dao(list_price: int, promo_price: int) -> None:
    # Ca thật ElevenLabs 21/10. Cả 22 và 11 đều có trong evidence, nên kiểm số không bắt được
    # lỗi đảo (lần 1 ghi 11/22); lỗi đảo chỉ do promo_above_list bắt. Evidence thật chỉ có giá,
    # không có tên plan, nên tên plan bị cảnh báo.
    data = good()
    data["pricing"]["plans"] = [
        fact(
            "src_02",
            "$22 First month 50% off\n$11per month",
            name="Creator",
            currency="USD",
            list_price=list_price,
            promo_price=promo_price,
            promo_terms="First month 50% off",
            price_unit="month",
            billing_cycle="monthly",
            price_text="$22 First month 50% off $11per month",
        )
    ]
    data["conflicts"] = []
    pages = {**PAGES, "pages/src_02-pricing-pricing.raw.md": CREATOR_MD}
    res, _ = run([ok(data)], pages=pages)
    assert isinstance(res, ExtractResult)
    value_warns = [w for w in res.warnings if w.startswith("value_not_in_evidence")]
    assert value_warns == ["value_not_in_evidence:pricing.plans[0].name"]
    assert ("promo_above_list:pricing.plans[0]" in res.warnings) == (promo_price > list_price)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$1,000/mo", {1000.0, 1.0}),
        ("1.000.000đ", {1000000.0}),
        ("9,99 €", {9.99}),
        ("$1,234.56", {1234.56}),
        ("$0.08 per 1K", {0.08, 1.0}),
    ],
)
def test_doc_so_trong_evidence(text: str, expected: set[float]) -> None:
    assert expected <= numbers_in(text)


def test_schema_gui_llm_dat_ten_san_pham_truoc_evidence() -> None:
    # LLM sinh theo thứ tự khoá; evidence trước value thì LLM lấy câu đầu trang (chạy thật 21/10)
    defs = PKBExtract.model_json_schema()["$defs"]
    assert defs["IdentityExtract"]["properties"]["name"] == {"$ref": "#/$defs/NameFact"}
    keys = list(defs["NameFact"]["properties"])
    assert keys.index("value") < keys.index("evidence")


# ---------------------------------------------------------------- tên sản phẩm (code tìm lại)
def name_warnings(res: ExtractResult) -> list[str]:
    return [w for w in res.warnings if w == "value_not_in_evidence:identity.name"]


def test_ten_khong_co_trong_evidence_thi_lay_h1_cua_trang_da_gui() -> None:
    data = good()
    data["identity"]["name"] = fact("src_01", "free online PDF toolkit", value="Acme PDF")
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    name = res.data["identity"]["name"]
    assert (name["value"], name["source_id"], name["evidence"]) == (
        "Acme PDF",
        "src_01",
        "Acme PDF",
    )
    assert "extracted_via" not in name  # h1 là chữ trong markdown
    assert not name_warnings(res)
    assert not [w for w in res.warnings if w.startswith("evidence_not_found")]


def test_ten_lay_tu_og_site_name_roi_title_trong_header() -> None:
    # "Acme Suite" chỉ có trong header của src_03 (h1 của src_01 là "Acme PDF")
    header = "<!-- source_id: src_03 | url: https://acme.example/features"
    header += " | title: Features - Acme Suite"
    site = " | site_name: Acme Suite"
    pages = {**PAGES, "pages/src_03-features-features.md": f"{header}{site} -->\n\n{FEATURES_MD}"}
    data = good()
    data["identity"]["name"] = fact("src_01", "free online PDF toolkit", value="Acme Suite")
    res, _ = run([ok(data)], pages=pages)
    assert isinstance(res, ExtractResult)
    name = res.data["identity"]["name"]
    assert (name["source_id"], name["evidence"], name["extracted_via"]) == (
        "src_03",
        "Acme Suite",
        "og",
    )
    assert not name_warnings(res)
    assert not [w for w in res.warnings if w.startswith("evidence_not_found")]
    # không có og:site_name thì dùng <title>
    pages["pages/src_03-features-features.md"] = f"{header} -->\n\n{FEATURES_MD}"
    res, _ = run([ok(data)], pages=pages)
    assert isinstance(res, ExtractResult)
    name = res.data["identity"]["name"]
    assert (name["evidence"], name["extracted_via"]) == ("Features - Acme Suite", "dom")


def test_ten_tim_o_trang_chua_gui_thi_them_vao_sources() -> None:
    pages = [
        record("src_01", "other", "home", 1000),
        record("src_02", "pricing", "pricing", 100),
        record("src_03", "features", "features", 80),
        record("src_04", "other", "about", 5),
    ]
    texts = {**PAGES, "pages/src_04-other-about.md": "# About Acme Cloud\nWe build tools."}
    data = good()
    data["identity"]["name"] = fact("src_01", "free online PDF toolkit", value="Acme Cloud")
    res, transport = run([ok(data)], crawl(pages), texts, ExtractSettings(top_pages=3))
    assert isinstance(res, ExtractResult)
    assert "SOURCE src_04" not in transport.calls[0]["prompt"]  # không gửi LLM
    assert res.data["identity"]["name"]["source_id"] == "src_04"
    assert [s["id"] for s in res.sources] == ["src_01", "src_02", "src_03", "src_04"]
    assert not name_warnings(res)
    validate_pkb(res.data, res.sources)


def test_ten_so_khop_theo_tu_khong_theo_chuoi_con() -> None:
    assert has_word("ElevenLabs", "ElevenLabs Mobile App")
    assert not has_word("ElevenLabs", "import { ElevenLabsClient }")
    assert not has_word("Pro", "Product")
    assert has_word("Công cụ", unicodedata.normalize("NFD", "# Công cụ PDF"))


def test_header_markdown_luu_title_site_name_va_doc_lai(tmp_path: Path) -> None:
    store = LocalPageStore(tmp_path)
    paths = store.save_page(
        source_id="src_01",
        url="https://acme.example/",
        page_type="other",
        fetched_at="2026-10-21T01:00:00+00:00",
        raw_md="# Acme",
        fit_md="# Acme",
        title="Acme | PDF tools -->",
        site_name="Acme",
    )
    meta = parse_header(store.read_page(paths.raw_path))
    assert meta["title"] == "Acme PDF tools" and meta["site_name"] == "Acme"
    assert meta["url"] == "https://acme.example/"


# ---------------------------------------------------------------- free-only
FREE_MD = "# Acme PDF\nHoàn toàn Miễn phí\nKhông đăng ký, không chi phí ẩn.\n"


def test_san_pham_chi_mien_phi_ghi_1_plan_free_khong_canh_bao_ten_plan() -> None:
    data = good()
    data["pricing"]["plans"] = [
        fact("src_02", "Hoàn toàn Miễn phí", name="Free", currency=None, list_price=0,
             price_unit="month", billing_cycle="monthly", price_text="Hoàn toàn Miễn phí")
    ]  # fmt: skip
    data["pricing"]["free_plan"] = fact("src_02", "Hoàn toàn Miễn phí", value=True)
    data["conflicts"] = []
    pages = {**PAGES, "pages/src_02-pricing-pricing.raw.md": FREE_MD}
    res, _ = run([ok(data)], pages=pages)
    assert isinstance(res, ExtractResult)
    assert not [w for w in res.warnings if w.startswith("value_not_in_evidence")]
    assert "free_only_placeholder_period:pricing.plans[0]" in res.warnings
    assert res.data["pricing"]["free_plan"]["value"] is True
    validate_pkb(res.data, res.sources)


def test_ngoai_le_free_only_khong_ap_dung_khi_co_nhieu_plan() -> None:
    data = good()
    data["pricing"]["plans"][0].update(name="Starter", evidence="Free $0 forever.")
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert "value_not_in_evidence:pricing.plans[0].name" in res.warnings
    assert not [w for w in res.warnings if w.startswith("free_only_placeholder_period")]


def test_gia_0_khop_chu_mien_phi() -> None:
    assert price_in_evidence(0, "Miễn phí Sử dụng")
    assert not price_in_evidence(0, "Không đăng ký, không chi phí ẩn.")


# ---------------------------------------------------------------- conflicts
def test_conflict_cua_llm_ghi_vao_quality_conflicts() -> None:
    res, _ = run([ok(good())])
    assert isinstance(res, ExtractResult)
    [c] = res.data["quality"]["conflicts"]
    assert c == {
        "field": "identity.description",
        "values": ["90+ tools", "100+ tools"],
        "source_ids": ["src_01", "src_03"],
    }
    assert "conflict:identity.description" in res.warnings


def test_conflict_field_khong_tro_toi_truong_nao_thi_canh_bao() -> None:
    data = good()
    data["conflicts"][0]["field"] = "identity.tool_count"
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert "conflict_field_unresolved:identity.tool_count" in res.warnings
    assert "conflict_field_unresolved:identity.description" not in run([ok(good())])[0].warnings  # type: ignore[union-attr]


def test_conflict_chi_1_gia_tri_hoac_trang_la_thi_bo() -> None:
    data = good()
    data["conflicts"][0]["claims"][1]["source_id"] = "src_77"
    data["conflicts"].append(
        {
            "field": "features",
            "topic": "x",
            "claims": [
                {"value": "a", "source_id": "src_01", "evidence": "Acme PDF"},
                {"value": "a ", "source_id": "src_03", "evidence": "Merge PDF"},
            ],
        }
    )
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert "quality" not in res.data


def test_code_phat_hien_gia_mau_thuan_cua_cung_plan() -> None:
    data = good()
    data["conflicts"] = []
    data["pricing"]["plans"].append(
        fact("src_03", "Acme PDF offers 100+ tools", name="Pro", currency="USD", list_price=12,
             price_unit="month", billing_cycle="monthly", price_text="$12 per month")
    )  # fmt: skip
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    plans = res.data["pricing"]["plans"]
    assert len(plans) == 4  # giữ cả 2 dòng, không chọn
    [c] = res.data["quality"]["conflicts"]
    assert c == {
        "field": "pricing.plans[1].list_price",
        "values": [9, 12],
        "source_ids": ["src_02", "src_03"],
    }


def test_bo_plan_khong_co_gia_khi_da_co_plan_cung_ten_kem_gia() -> None:
    data = good()
    data["pricing"]["plans"].append(fact("src_01", "Acme PDF", name="Pro", price_text="Pro plan"))
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert len(res.data["pricing"]["plans"]) == 3


# ---------------------------------------------------------------- lỗi
def test_het_rpd_tra_llm_quota_daily_kem_retry_after_va_chi_phi() -> None:
    rpd = json.loads((FIXTURES / "error-429-rpd.json").read_text(encoding="utf-8"))
    res, _ = run([rpd])
    assert isinstance(res, ExtractError)
    assert res.code is LLMErrorCode.QUOTA_DAILY and res.retryable
    assert res.retry_after == datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    [item] = res.cost_breakdown["items"]
    assert item["cost_usd"] == 0 and item["cost_status"] == "estimated"


def test_rpm_retry_roi_thanh_cong_co_2_item_chi_phi() -> None:
    rpm = json.loads((FIXTURES / "error-429-rpm.json").read_text(encoding="utf-8"))
    res, _ = run([rpm, ok(good())])
    assert isinstance(res, ExtractResult)
    assert [i["attempt"] for i in res.cost_breakdown["items"]] == [1, 2]
    assert any(w.startswith("llm_retried:1") for w in res.warnings)


def test_output_sai_schema_tra_llm_invalid_output_kem_chi_phi() -> None:
    data = good()
    del data["identity"]["name"]
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractError)
    assert res.code is LLMErrorCode.INVALID_OUTPUT and not res.retryable
    assert len(res.cost_breakdown["items"]) == 1


def test_ten_san_pham_tro_toi_trang_la_tra_llm_invalid_output() -> None:
    data = good()
    data["identity"]["name"]["source_id"] = "src_55"
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractError) and res.code is LLMErrorCode.INVALID_OUTPUT


@pytest.mark.parametrize("status", ["failed"])
def test_crawl_failed_khong_goi_llm(status: str) -> None:
    res, transport = run([ok(good())], crawl(status=status))
    assert isinstance(res, ExtractError) and res.code is ExtractErrorCode.NO_PAGES
    assert transport.calls == [] and res.cost_breakdown["items"] == []


def test_khong_co_trang_doc_duoc() -> None:
    res, transport = run([ok(good())], crawl([]))
    assert isinstance(res, ExtractError) and res.code is ExtractErrorCode.NO_PAGES
    assert transport.calls == []
