"""Test sửa plan (giá khuyến mãi, tên plan) và chuẩn hoá field của conflicts. Dữ liệu giả theo mẫu
trang một trang AISoEasy 29/10 (mục giá nằm trên trang chủ), không phải HTML thật."""

from __future__ import annotations

from typing import Any

import pytest

from worker.m1.extract import ExtractResult
from worker.m1.extract.evidence import currency_prices, has_promo_marker
from worker.m1.extract.plans import split_promo
from worker.m1.extract.service import _fact_path
from worker.m1.pkb.validate import validate_pkb

from .test_extract import crawl, fact, good, ok, record, run

NOVA_RAW = """# Nova Learn
Membership
## Learn for free — or unlock every opportunity with Pro
  * Shared AI lesson library

### Individual Free
Free learning, core content only
Free
no credit card required
  * Watch lessons

[Start for free](https://nova.example/signup)
50% off — limited spots
### Individual Pro
For individuals who want results
$9$18
/ month — 50% off, limited spots
  * Join quests
  * Member discounts on courses

Join now — $9/month
### Business / Team
Roll out to your entire workforce
Contact sales
priced case by case
  * All Pro benefits
"""
# fit làm rơi tiêu đề plan và dòng giá, giữ dòng "Join now"
NOVA_FIT = """# Nova Learn
## Learn for free — or unlock every opportunity with Pro
  * Shared AI lesson library

Free learning, core content only
no credit card required
  * Watch lessons

50% off — limited spots
For individuals who want results
/ month — 50% off, limited spots
  * Join quests

Join now — $9/month
### Business / Team
Roll out to your entire workforce
priced case by case
  * All Pro benefits
"""
HOME = {"pages/src_01-other-home.md": NOVA_FIT, "pages/src_01-other-home.raw.md": NOVA_RAW}


def plan(name: str, evidence: str, price: float | None, **kw: Any) -> dict[str, Any]:
    base = {
        "name": name,
        "currency": "USD" if price else None,
        "list_price": price,
        "price_unit": "month" if price is not None else None,
        "billing_cycle": "monthly" if price is not None else None,
        "price_text": evidence,
    }
    return fact("src_01", evidence, **{**base, **kw})


def nova() -> dict[str, Any]:
    d = good()
    d["identity"] = {"name": fact("src_01", "Nova Learn", value="Nova Learn"), "models": []}
    d["features"] = []
    d["conflicts"] = []
    d["pricing"]["plans"] = [
        plan("Free", "Free learning, core content only", 0),
        plan("Pro", "Join now — $9/month", 9),  # lỗi thật: bỏ $18 và khuyến mãi
        plan("Business / Team", "Roll out to your entire workforce", None),
    ]
    return d


def run_nova(data: dict[str, Any], pages: dict[str, str]) -> ExtractResult:
    res, _ = run([ok(data)], crawl([record("src_01", "other", "home", 1000)]), pages)
    assert isinstance(res, ExtractResult)
    return res


# ---------------------------------------------------------------- raw thay fit
def test_trang_other_gui_raw_khi_raw_co_gia_ma_fit_roi() -> None:
    res, transport = run([ok(nova())], crawl([record("src_01", "other", "home", 1000)]), HOME)
    assert isinstance(res, ExtractResult)
    assert "$9$18" in transport.calls[0]["prompt"]
    [src] = res.sources
    assert (src["variant"], src["markdown_path"]) == ("raw", "pages/src_01-other-home.raw.md")


def test_trang_other_gui_fit_khi_raw_khong_them_gia() -> None:
    res, transport = run([ok(good())])
    assert isinstance(res, ExtractResult)
    assert {s["id"]: s["variant"] for s in res.sources}["src_01"] == "fit"
    assert "SOURCE src_01" in transport.calls[0]["prompt"]


# ---------------------------------------------------------------- giá khuyến mãi
def test_ca_aisoeasy_tach_gia_niem_yet_va_khuyen_mai_va_lay_ten_plan_tu_heading() -> None:
    res = run_nova(nova(), HOME)
    free, pro, biz = res.data["pricing"]["plans"]
    assert (pro["list_price"], pro["promo_price"], pro["promo_terms"]) == (18, 9, "limited spots")
    assert pro["name"] == "Pro"  # value giữ nguyên, chỉ evidence đổi
    assert pro["evidence"].startswith("### Individual Pro\n") and "$9$18" in pro["evidence"]
    assert pro["price_text"] == "$9$18 / month — 50% off, limited spots"
    assert biz["evidence"].startswith("### Business / Team\n")
    assert free["list_price"] == 0
    assert "promo_split:pricing.plans[1]" in res.warnings
    bad = ("value_not_in_evidence", "evidence_not_found", "promo_above_list", "promo_missing")
    assert not [w for w in res.warnings if w.startswith(bad)]
    validate_pkb(res.data, res.sources)


def test_khong_co_heading_chua_ten_thi_giu_warning_va_khong_doan_gia() -> None:
    # Chỉ có fit: không có `### Individual Pro`, heading gần nhất là "…with Pro" nhưng đoạn từ đó
    # tới dòng giá không có giá nằm trong 200 ký tự → giữ evidence cũ.
    pages = {"pages/src_01-other-home.md": NOVA_FIT}
    r = record("src_01", "other", "home", 1000, raw_path=None)
    res, _ = run([ok(nova())], crawl([r]), pages)
    assert isinstance(res, ExtractResult)
    pro = res.data["pricing"]["plans"][1]
    assert (pro["evidence"], pro["list_price"], pro.get("promo_price")) == (
        "Join now — $9/month",
        9,
        None,
    )
    assert "value_not_in_evidence:pricing.plans[1].name" in res.warnings


def test_evidence_co_ten_nhung_chi_1_gia_ma_khoi_co_2_gia_thi_promo_missing() -> None:
    data = nova()
    data["pricing"]["plans"][1].update(evidence="Individual Pro", name="Pro")
    res = run_nova(data, HOME)
    pro = res.data["pricing"]["plans"][1]
    assert (pro["list_price"], pro.get("promo_price")) == (9, None)  # không đoán từ khối
    assert "promo_missing:pricing.plans[1]" in res.warnings


def test_plan_da_co_promo_thi_khong_dong_vao() -> None:
    data = nova()
    data["pricing"]["plans"][1].update(
        evidence="### Individual Pro\nFor individuals who want results\n$9$18",
        list_price=18,
        promo_price=9,
        promo_terms="giới hạn",
    )
    res = run_nova(data, HOME)
    pro = res.data["pricing"]["plans"][1]
    assert (pro["list_price"], pro["promo_price"], pro["promo_terms"]) == (18, 9, "giới hạn")
    assert not [w for w in res.warnings if w.startswith("promo_")]


@pytest.mark.parametrize(
    ("evidence", "list_price", "expected", "prices"),
    [
        ("$9$18\n/ month — 50% off, limited spots", 9, "split", (18, 9)),
        ("$9$18\n/ month", 18, "split", (18, 9)),  # liền nhau, không cần dấu hiệu
        ("$18 now $9 / month, giảm giá 50%", 18, "split", (18, 9)),
        ("$22 First month 50% off\n$11per month", 11, "split", (22, 11)),
        # 3 giá khác chu kỳ: không phải khuyến mãi, dù có chữ "discount"
        (
            "Pro $17 with annual discount ($200 billed up front), $20 if billed monthly",
            17,
            "none",
            None,
        ),
        ("Pro $9 per month or $90 per year", 9, "none", None),  # 2 giá khác đơn vị, không dấu hiệu
        ("Pro $9/month or $90/year, 20% off", 9, "unparsed", None),  # khác đơn vị + dấu hiệu
        ("Pro $20/month — 50% off", 20, "unparsed", None),  # dấu hiệu nhưng chỉ 1 giá
        ("$9$18 / month", 12, "unparsed", None),  # giá LLM ghi không thuộc cặp
        ("Contact sales", None, "none", None),
        ("Contact sales for 50% off", None, "none", None),
    ],
)
def test_split_promo(
    evidence: str, list_price: float | None, expected: str, prices: tuple[float, float] | None
) -> None:
    p = fact("src_01", evidence, name="Pro", list_price=list_price, promo_price=None)
    assert split_promo(p) == expected
    if prices:
        assert (p["list_price"], p["promo_price"]) == prices


def test_so_tran_khong_phai_gia_va_contact_sales_khong_phai_khuyen_mai() -> None:
    assert [t.value for t in currency_prices("50% off — $9/month, 10 seats")] == [9]
    assert [t.value for t in currency_prices("100.000đ/tháng")] == [100000]
    assert [t.value for t in currency_prices("9,99 €")] == [9.99]
    assert not has_promo_marker("Contact sales")
    assert has_promo_marker("50% off — limited spots") and has_promo_marker("Giảm giá 20%")


# ---------------------------------------------------------------- conflicts (#83)
def with_conflict(field: str, claims: list[tuple[str, str, str]]) -> dict[str, Any]:
    data = good()
    data["conflicts"] = [
        {
            "field": field,
            "topic": "số lượng công cụ",
            "claims": [{"value": v, "source_id": s, "evidence": e} for v, s, e in claims],
        }
    ]
    return data


CLAIMS = [
    ("90+ tools", "src_01", "with 90+ tools"),
    ("100+ tools", "src_03", "offers 100+ tools"),
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("identity.description.value", "identity.description"),
        ("identity.description.evidence", "identity.description"),
        ("features[1].source_id", "features[1]"),
        ("identity.name.value.evidence", "identity.name"),
        ("pricing.plans[0].list_price", "pricing.plans[0].list_price"),
        ("specs[5].value", "specs[5].value"),  # physical: `value` là trường dữ liệu
    ],
)
def test_fact_path_bo_hau_to(raw: str, expected: str) -> None:
    assert _fact_path(raw) == expected


def test_conflict_cua_llm_bo_hau_to_value_truoc_khi_luu() -> None:
    res, _ = run([ok(with_conflict("identity.description.value", CLAIMS))])
    assert isinstance(res, ExtractResult)
    [c] = res.data["quality"]["conflicts"]
    assert c["field"] == "identity.description"
    assert "conflict:identity.description" in res.warnings
    assert not [w for w in res.warnings if w.startswith("conflict_field_unresolved")]


def test_conflict_o_muc_ca_mang_thi_thu_hep_ve_fact_ma_claim_noi_toi() -> None:
    res, _ = run([ok(with_conflict("features", CLAIMS))])
    assert isinstance(res, ExtractResult)
    [c] = res.data["quality"]["conflicts"]
    assert c["field"] == "identity.description"
    assert not [w for w in res.warnings if w.startswith("conflict_too_broad")]


def test_conflict_o_muc_ca_mang_khong_thu_hep_duoc_thi_giu_va_canh_bao() -> None:
    claims = [
        ("100+ tools", "src_03", "offers 100+ tools"),
        ("130 tools", "src_03", "for every task"),
    ]
    res, _ = run([ok(with_conflict("features", claims))])
    assert isinstance(res, ExtractResult)
    [c] = res.data["quality"]["conflicts"]
    assert c["field"] == "features"
    assert "conflict_too_broad:features" in res.warnings


def test_conflict_khong_chung_minh_mot_fact_khi_claim_noi_toi_2_fact() -> None:
    data = with_conflict(
        "features",
        [
            ("Merge PDF", "src_03", "Merge PDF: combine many files into one."),
            ("Nén", "src_03", "Công cụ nén PDF giúp giảm dung lượng tệp."),
        ],
    )
    res, _ = run([ok(data)])
    assert isinstance(res, ExtractResult)
    assert res.data["quality"]["conflicts"][0]["field"] == "features"
    assert "conflict_too_broad:features" in res.warnings
