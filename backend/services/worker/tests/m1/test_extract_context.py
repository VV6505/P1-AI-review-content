"""Test ngữ cảnh khối nguồn cho evidence (usp / use_cases / audiences) và số liệu có dấu `+`.
Trang giả theo mẫu trang chủ one-page, không phải dữ liệu thật."""

from __future__ import annotations

import unicodedata
from typing import Any

import pytest

from worker.m1.extract import ExtractResult
from worker.m1.extract.context import add_block_context
from worker.m1.extract.coverage import split_sections
from worker.m1.extract.evidence import EvidenceIndex, has_metric, metric_warnings
from worker.m1.extract.prompt import SYSTEM_PROMPT
from worker.m1.pkb.models import EVIDENCE_MAX

from .test_extract import fact
from .test_extract_coverage import HOME, SALES, doc, nova, run_nova

PAGE = """Workforce platform by Nova
# The upskilling platform for small teams
Helping small businesses build smarter, more productive teams with practical AI skills today, \
with lessons, grading and certificates for every single employee.
Start now
5.06M+
    content views
## Nova already has a community
### TikTok
The Virality Engine
2.58M+ Views
35k+ followers, average 36k views per video.
### Facebook Group
The Advocate Cult
1,867+
elite members, +720 in H1 — deep discussions on tools.
~250videos & posts deployed87.6%audience in Vietnam
## Learn
For individuals
## Free AI videos? Here is what you are missing.
Free videos only show you how.
## Tools
**90+ tools** for every job.
```
# not a heading
fenced line 7M+ views
```
"""
D = doc(PAGE)


def run_ctx(group: str, *facts: dict[str, Any], text: str = PAGE) -> tuple[list[Any], list[str]]:
    pkb = {group: list(facts)}
    return pkb[group], add_block_context(pkb, [doc(text)])


def test_usp_giua_khoi_noi_heading_vao_evidence_va_ten_khoi_vao_text() -> None:
    [f], warnings = run_ctx(
        "usp", fact("src_01", "2.58M+ Views", text="Theo Nova công bố: 2.58M+ Views")
    )
    assert f["evidence"] == "### TikTok\nThe Virality Engine\n2.58M+ Views"
    assert f["text"] == "Theo Nova công bố: 2.58M+ Views (TikTok)"
    assert warnings == []


def test_ten_khoi_da_co_trong_text_thi_khong_them() -> None:
    [f], _ = run_ctx("usp", fact("src_01", "2.58M+ Views", text="Theo Nova công bố: TikTok 2.58M+"))
    assert f["text"] == "Theo Nova công bố: TikTok 2.58M+"
    assert f["evidence"].startswith("### TikTok")


def test_evidence_ket_thuc_giua_dong_thi_chi_mo_rong_ve_phia_tren() -> None:
    [f], _ = run_ctx("usp", fact("src_01", "35k+ followers", text="x"))
    assert f["evidence"] == "### TikTok\nThe Virality Engine\n2.58M+ Views\n35k+ followers"


def test_so_di_kem_dong_giua_cau_van_lay_ca_cau_tu_heading() -> None:
    [f], _ = run_ctx("usp", fact("src_01", "+720 in H1", text="Theo Nova công bố: +720 in H1"))
    assert (
        f["evidence"] == "### Facebook Group\nThe Advocate Cult\n1,867+\nelite members, +720 in H1"
    )
    assert f["text"].endswith("(Facebook Group)")


@pytest.mark.parametrize(
    "evidence",
    [
        "TikTok\nThe Virality Engine",  # bắt đầu ngay trong dòng heading
        "### Facebook Group\nThe Advocate Cult",  # đã có cả dấu #
        "For individuals\nFree AI videos? Here is what you are missing.",  # vắt qua heading
    ],
)
def test_evidence_da_chua_heading_thi_khong_doi(evidence: str) -> None:
    [f], warnings = run_ctx("audiences", fact("src_01", evidence, segment="x"))
    assert f["evidence"] == evidence
    assert warnings == []


def test_heading_xa_qua_200_ky_tu_thi_giu_evidence_cu_va_canh_bao() -> None:
    f1 = fact("src_01", "5.06M+\n    content views", text="Theo Nova công bố: 5.06M+ content views")
    [f1], w1 = run_ctx("usp", f1)  # hero: H1 cách số liệu quá xa
    f2 = fact("src_01", SALES, title="Sales: Close deals faster with AI")
    [f2], w2 = run_ctx("use_cases", f2, text=HOME)  # tên phòng ban, tiêu đề, kết quả
    assert (w1, w2) == (
        ["evidence_context_missing:usp[0]"],
        ["evidence_context_missing:use_cases[0]"],
    )
    assert f1["evidence"] == "5.06M+\n    content views"
    assert f2["evidence"] == SALES
    assert f1["text"] == "Theo Nova công bố: 5.06M+ content views"  # không thêm tên khi chưa nối


def test_dong_so_lieu_cua_ca_trang_sau_khoi_khong_bi_gan_cho_khoi() -> None:
    """Dòng thống kê chung nằm sau khối `### Facebook Group` (ca `87.6%audience in Vietnam`):
    cách heading quá 3 dòng thân thì không phải của khối, giữ evidence cũ."""
    f = fact("src_01", "87.6%audience in Vietnam", text="Theo Nova công bố: 87.6% audience")
    [f], warnings = run_ctx("usp", f)
    assert (f["evidence"], f["text"]) == (
        "87.6%audience in Vietnam",
        "Theo Nova công bố: 87.6% audience",
    )
    assert warnings == ["evidence_context_missing:usp[0]"]


def test_heading_la_cau_dai_thi_noi_evidence_nhung_khong_them_vao_text() -> None:
    page = "## Partner with us to bring AI adoption to millions of SMEs\n5M+\nview infrastructure\n"
    [f], warnings = run_ctx("usp", fact("src_01", "5M+\nview infrastructure", text="t"), text=page)
    assert f["evidence"] == page.strip()
    assert (f["text"], warnings) == ("t", [])


def test_evidence_la_chinh_dong_heading_thi_noi_dong_nhan_ngan_ngay_tren() -> None:
    """Nhãn (kicker) đứng ngay trên heading: `For AI Brands…` trên `## Partner with us…`."""
    [f], warnings = run_ctx(
        "audiences", fact("src_01", "Free AI videos? Here is what you are", segment="x")
    )
    assert f["evidence"] == "For individuals\n## Free AI videos? Here is what you are"
    assert warnings == []


@pytest.mark.parametrize(
    "above",
    [
        "+28% operational productivity",  # có chữ số
        "  * Product link",  # mục danh sách
        "> a quote",
        "# Parent heading",  # là heading khác
        "Helping small businesses build smarter teams today.",  # câu dài, có dấu chấm
        "One two three four five six seven",  # > 6 từ
    ],
)
def test_dong_tren_heading_khong_phai_nhan_thi_khong_noi(above: str) -> None:
    page = f"{above}\n## Partner with us\nBring AI to SMEs.\n"
    [f], _ = run_ctx("audiences", fact("src_01", "Partner with us", segment="x"), text=page)
    assert f["evidence"] == "Partner with us"


def test_heading_o_dau_trang_khong_co_dong_nhan() -> None:
    [f], _ = run_ctx(
        "audiences", fact("src_01", "Partner with us", segment="x"), text="## Partner with us\nHi\n"
    )
    assert f["evidence"] == "Partner with us"


def test_khong_co_heading_phia_tren_thi_khong_lam_gi() -> None:
    [f], warnings = run_ctx("usp", fact("src_01", "Workforce platform by Nova", text="x"))
    assert (f["evidence"], f["text"], warnings) == ("Workforce platform by Nova", "x", [])


def test_evidence_khong_co_trong_trang_thi_de_cho_evidence_not_found() -> None:
    [f], warnings = run_ctx("usp", fact("src_01", "9M+ downloads", text="x"))
    assert (f["evidence"], warnings) == ("9M+ downloads", [])


def test_fact_trang_khac_hoac_khong_phai_nhom_ngu_canh_thi_bo_qua() -> None:
    other = fact("src_09", "2.58M+ Views", text="x")
    feat = fact("src_01", "2.58M+ Views", name="x")
    pkb = {"usp": [other], "features": [feat]}
    assert add_block_context(pkb, [doc(PAGE)]) == []
    assert (other["evidence"], feat["evidence"]) == ("2.58M+ Views", "2.58M+ Views")


def test_evidence_bi_llm_bo_dau_markdown_van_noi_dung_nguyen_van() -> None:
    [f], _ = run_ctx("usp", fact("src_01", "90+ tools for every job.", text="x"))
    assert f["evidence"] == "## Tools\n**90+ tools** for every job."


def test_dong_trong_khoi_code_khong_phai_heading() -> None:
    page = "## Tools\n```\n# not a heading\nfenced line 7M+ views\n```\n"
    [f], _ = run_ctx("usp", fact("src_01", "fenced line 7M+ views", text="x"), text=page)
    assert f["evidence"] == "## Tools\n```\n# not a heading\nfenced line 7M+ views"


def test_chuoi_unicode_to_hop_van_dinh_vi_dung() -> None:
    text = unicodedata.normalize("NFD", "# Mạng xã hội\nLượt xem\n2,5 triệu lượt xem trên TikTok\n")
    [f], _ = run_ctx("usp", fact("src_01", "2,5 triệu lượt xem", text="x"), text=text)
    assert f["evidence"] == unicodedata.normalize(
        "NFD", "# Mạng xã hội\nLượt xem\n2,5 triệu lượt xem"
    )


def test_evidence_moi_nguyen_van_trong_nguon_va_khong_qua_gioi_han() -> None:
    facts = [
        fact("src_01", "2.58M+ Views", text="x"),
        fact("src_01", "35k+ followers", text="x"),
        fact("src_01", "+720 in H1", text="x"),
        fact("src_01", "90+ tools for every job.", text="x"),
    ]
    run_ctx("usp", *facts)
    index = EvidenceIndex({"src_01": D.index_text})
    assert all(index.found("src_01", f["evidence"]) for f in facts)
    assert all(len(f["evidence"]) <= EVIDENCE_MAX for f in facts)


def test_dung_ranh_gioi_heading_cua_split_sections() -> None:
    """Heading ở context trùng tiêu đề section mà độ phủ dùng (cùng cách đọc heading)."""
    sections, _ = split_sections("src_01", PAGE)
    assert {"TikTok", "Facebook Group"} <= {s.heading for s in sections}


# ---------------------------------------------------------------- qua extract_product
def test_extract_noi_ngu_canh_va_canh_bao_khi_khong_noi_duoc() -> None:
    data = nova()
    data["usp"] = [
        fact("src_01", "35k+ followers, average 36k views per video", text="Theo Nova: 35k+")
    ]
    data["use_cases"] = [fact("src_01", SALES, title="Sales: Close deals faster with AI")]
    res: ExtractResult = run_nova(data)
    assert res.data["usp"][0]["evidence"].startswith("### TikTok\n")
    assert res.data["usp"][0]["text"].endswith("(TikTok)")
    assert res.data["use_cases"][0]["evidence"] == SALES
    assert "evidence_context_missing:use_cases[0]" in res.warnings
    assert "evidence_context_missing:usp[0]" not in res.warnings
    assert "evidence_not_found:usp[0]" not in res.warnings


# ---------------------------------------------------------------- số liệu có dấu +
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+720 in H1", True),
        ("elite members, +720 in H1", True),
        ("+35% more opportunities", True),
        ("C++11 support", False),
        ("Pro 10 seats", False),
    ],
)
def test_has_metric_so_co_dau_cong(text: str, expected: bool) -> None:
    assert has_metric(text) is expected


def test_usp_chi_co_so_cong_van_bi_gan_self_reported_metric() -> None:
    pkb = {"usp": [fact("src_01", "+720 in H1", text="Theo Nova công bố: +720 in H1")]}
    assert metric_warnings(pkb) == ["self_reported_metric:usp[0]"]


def test_moi_usp_va_use_case_co_so_deu_co_warning() -> None:
    pkb = {
        "usp": [
            fact("src_01", "2.58M+ Views", text="a"),
            fact("src_01", "+720 in H1", text="b"),
            fact("src_01", "Verifiable certificates", text="c"),
        ],
        "use_cases": [fact("src_01", SALES, title="Sales"), fact("src_01", "5x output", title="M")],
    }
    assert metric_warnings(pkb) == [
        "self_reported_metric:usp[0]",
        "self_reported_metric:usp[1]",
        "self_reported_metric:use_cases[0]",
        "self_reported_metric:use_cases[1]",
    ]


# ---------------------------------------------------------------- prompt
def test_prompt_huong_dan_challenge_employees_va_nhan_day_du() -> None:
    for needle in (
        "Weekly Challenge",  # khối ngắn heading + 1 câu mô tả là 1 feature
        "Employees",  # audience nhân viên theo phòng ban, jtbd null
        "active members",  # số kèm giữ nhãn đầy đủ của câu nguồn
    ):
        assert needle in SYSTEM_PROMPT
