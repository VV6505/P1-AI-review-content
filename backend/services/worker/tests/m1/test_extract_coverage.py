"""Test độ phủ section, cảnh báo số liệu tự công bố, audiences / usp. Trang giả theo mẫu trang chủ
one-page (hero, traction, lộ trình theo phòng ban, jobs board), không phải HTML thật."""

from __future__ import annotations

from typing import Any

import pytest

from worker.m1.extract import ExtractResult
from worker.m1.extract.coverage import (
    TOP,
    coverage_warnings,
    split_sections,
    uncovered_sections,
)
from worker.m1.extract.evidence import has_metric, iter_facts, label_mismatch, metric_warnings
from worker.m1.extract.pages import SourceDoc
from worker.m1.extract.prompt import SYSTEM_PROMPT, clean_for_llm
from worker.m1.extract.schema import PKBExtract
from worker.m1.extract.service import ExtractSettings
from worker.m1.pkb.validate import validate_pkb

from .test_extract import crawl, fact, good, ok, record, run

HOME = """[Nova](https://nova.example/#top)
  * [Product](https://nova.example/#product)
  * [Pricing](https://nova.example/#pricing)
Learning platform by Nova
# The upskilling platform for small teams
Helping small businesses build smarter, more productive teams with practical AI skills today.
Start now
5.06M+
    content views 33,973+
    new followers
## Nova already has a community
More than a learning platform, Nova built a content ecosystem with large reach and a loyal \
audience of learners across the whole country.
### TikTok
The Virality Engine
2.58M+ Views
35k+ followers, average 36k views per video, top of funnel discovery at scale.
## Training built for real jobs
Sales
### Close deals faster with AI
Level
Beginner to Advanced
Learning path
  1. Research prospects with AI
  2. Draft emails and sales scripts
  3. Summarize calls and track the pipeline
+35% more opportunities handled per week
Marketing
### Create more content in less time
Level
Beginner to Expert
Learning path
  1. Content ideas and calendar
  2. Write copy, images and video with AI
  3. Measure and optimize campaigns
5x content output
## Find your next role with AI skills
Internships, part-time and full-time openings from companies training their teams on Nova.
[Browse all jobs](https://nova.example/jobs)
## Build a smarter workforce today
[Upgrade my team](https://nova.example/signup)
Product
  * [Learning Hub](https://nova.example/#product)
  * [Paths](https://nova.example/#paths)
  * [Pricing](https://nova.example/#pricing)
Legal
  * [Privacy Policy](https://nova.example/privacy)
  * [Terms of Service](https://nova.example/terms)
"""
INTRO = (
    "Helping small businesses build smarter, more productive teams with practical AI skills today."
)
COMMUNITY = "More than a learning platform, Nova built a content ecosystem"
JOBS = "Internships, part-time and full-time openings from companies training their teams on Nova."
SALES = "+35% more opportunities handled per week"
PAGES = {"pages/src_01-other-home.md": HOME, "pages/src_01-other-home.raw.md": HOME}


CLEAN = clean_for_llm(HOME)  # `SourceDoc.text` đã bỏ ảnh, URL của link và dòng trống


def doc(text: str = CLEAN, source_id: str = "src_01", page_type: str = "other") -> SourceDoc:
    return SourceDoc(
        source_id=source_id,
        url="https://nova.example/",
        page_type=page_type,
        score=1000,
        fetched_at="2026-10-30T01:00:00+00:00",
        region="VN",
        locale="en-US",
        variant="fit",
        content_hash="sha256:x",
        path=f"pages/{source_id}.md",
        text=text,
    )


def facts_of(*evidence: str, sid: str = "src_01") -> list[tuple[str, dict[str, Any]]]:
    return [(f"features[{i}]", fact(sid, e)) for i, e in enumerate(evidence)]


def headings(missed: list[Any]) -> list[str]:
    return [s.heading for s in missed]


# ---------------------------------------------------------------- tách section
def test_tach_section_theo_moi_heading_va_phan_dau_trang() -> None:
    sections, _ = split_sections("src_01", CLEAN)
    assert [s.heading for s in sections] == [
        TOP,
        "The upskilling platform for small teams",
        "Nova already has a community",
        "TikTok",
        "Training built for real jobs",
        "Close deals faster with AI",
        "Create more content in less time",
        "Find your next role with AI skills",
        "Build a smarter workforce today",
    ]
    # section cha chỉ giữ chữ trước heading con đầu tiên
    by = {s.heading: s for s in sections}
    assert by["Training built for real jobs"].body.strip() == "Sales"


def test_heading_la_link_lay_chu_cua_link_va_khoi_code_khong_phai_heading() -> None:
    md = "### [Close deals](https://x.example/a)\ntext\n```\n# not a heading\n```\nmore\n"
    sections, _ = split_sections("src_01", md)
    assert [s.heading for s in sections] == ["Close deals"]  # TOP trống thì bỏ


def test_page_text_bang_norm_cua_ca_trang() -> None:
    from worker.m1.extract.evidence import norm

    sections, page_text = split_sections("src_01", CLEAN)
    assert page_text == norm(CLEAN)
    assert sections[0].start == 0 and sections[-1].end == len(page_text)


def test_section_dang_ke_la_section_du_15_tu_con_menu_va_footer_ngan_thi_khong() -> None:
    sections, _ = split_sections("src_01", CLEAN)
    by = {s.heading: s for s in sections}
    assert by["Close deals faster with AI"].significant
    assert by["Find your next role with AI skills"].significant
    footer = by["Build a smarter workforce today"]
    assert (footer.words, footer.significant) == (14, False)  # nút + menu footer
    assert not sections[0].significant  # menu đầu trang


# ---------------------------------------------------------------- phủ
def test_khong_fact_nao_thi_moi_section_dang_ke_deu_bi_bao() -> None:
    missed = uncovered_sections([doc()], [])
    assert headings(missed) == [
        "The upskilling platform for small teams",
        "Nova already has a community",
        "TikTok",
        "Close deals faster with AI",
        "Create more content in less time",
        "Find your next role with AI skills",
    ]


def test_evidence_nam_trong_section_thi_section_do_duoc_phu() -> None:
    missed = uncovered_sections([doc()], facts_of(INTRO, SALES))
    assert "Close deals faster with AI" not in headings(missed)
    assert "The upskilling platform for small teams" not in headings(missed)
    assert "Create more content in less time" in headings(missed)


def test_evidence_vat_qua_hai_section_thi_phu_ca_hai() -> None:
    # cuối "Create more content…" + heading của "Find your next role…", mỗi bên ≥ 20 ký tự
    ev = "Measure and optimize campaigns\n5x content output\n## Find your next role with AI"
    missed = uncovered_sections([doc()], facts_of(ev))
    assert "Create more content in less time" not in headings(missed)
    assert "Find your next role with AI skills" not in headings(missed)


def test_evidence_chi_lan_sang_section_ke_vai_ky_tu_thi_khong_phu_section_do() -> None:
    # "Membership" là nhãn cuối section trước, ngay trên heading của section sau (ca AISoEasy)
    ev = "content views 33,973+\nnew followers\n## Nova already"
    missed = headings(uncovered_sections([doc()], facts_of(ev)))
    assert "The upskilling platform for small teams" not in missed  # phủ phần lớn
    assert "Nova already has a community" in missed  # chỉ lấn 12 ký tự
    # evidence ngắn nằm trọn trong section thì vẫn phủ
    covered = uncovered_sections([doc()], facts_of("Nova already has"))
    assert "Nova already has a community" not in headings(covered)


def test_evidence_khop_sau_chuan_hoa_markdown() -> None:
    missed = uncovered_sections([doc()], facts_of("**+35%** more opportunities handled per WEEK"))
    assert "Close deals faster with AI" not in headings(missed)


def test_evidence_ngan_lap_nhieu_noi_chi_phu_lan_xuat_hien_dau() -> None:
    # "Nova" có ở menu, hero, TikTok, jobs… nhưng fact tên sản phẩm không được phủ hết các khối đó
    missed = uncovered_sections([doc()], facts_of("Nova"))
    assert "Find your next role with AI skills" in headings(missed)
    assert "Nova already has a community" in headings(missed)


def test_fact_cua_trang_khac_khong_phu_section_cua_trang_nay() -> None:
    missed = uncovered_sections([doc()], facts_of(SALES, sid="src_02"))
    assert "Close deals faster with AI" in headings(missed)


def test_trang_khong_co_heading_dang_ke_thi_khong_bao() -> None:
    assert uncovered_sections([doc("# Nova\nA short page.\n")], []) == []


def test_coverage_warnings_dat_ten_theo_heading() -> None:
    data = {"features": [fact("src_01", JOBS, name="Jobs")]}
    ws = coverage_warnings([doc()], data)
    assert "section_not_covered:Nova already has a community" in ws
    assert "section_not_covered:Find your next role with AI skills" not in ws


# ---------------------------------------------------------------- qua extract_product
def nova() -> dict[str, Any]:
    d = good()
    d["identity"] = {
        "name": fact("src_01", "Learning platform by Nova", value="Nova"),
        "models": [],
    }
    d["pricing"] = {"plans": [], "usage_prices": [], "other_views": []}
    d["features"] = [fact("src_01", JOBS, name="Jobs board", description="Openings")]
    d["use_cases"] = []
    d["conflicts"] = []
    return d


def run_nova(data: dict[str, Any], settings: ExtractSettings | None = None) -> ExtractResult:
    rec = record("src_01", "other", "home", 1000)
    res, _ = run([ok(data)], crawl([rec]), PAGES, settings)
    assert isinstance(res, ExtractResult)
    return res


def test_extract_bao_section_chua_phu_cua_trang_chu() -> None:
    res = run_nova(nova())
    sw = [w for w in res.warnings if w.startswith("section_not_covered:")]
    assert "section_not_covered:Close deals faster with AI" in sw
    assert "section_not_covered:Nova already has a community" in sw
    assert "section_not_covered:Find your next role with AI skills" not in sw


def test_section_duoc_phu_thi_het_warning() -> None:
    data = nova()
    data["use_cases"] = [
        fact("src_01", SALES, title="Sales: Close deals faster with AI"),
        fact("src_01", "5x content output", title="Marketing: Create more content in less time"),
    ]
    data["usp"] = [
        fact("src_01", COMMUNITY, text="Theo Nova công bố: content ecosystem"),
        fact(
            "src_01",
            "35k+ followers, average 36k views per video",
            text="Theo Nova công bố: TikTok",
        ),
    ]
    data["features"] += [fact("src_01", INTRO, name="Teams", description="x")]
    res = run_nova(data)
    assert not [w for w in res.warnings if w.startswith("section_not_covered")]


def test_chi_kiem_trang_other_theo_mac_dinh_va_doi_duoc_bang_settings() -> None:
    rec = record("src_01", "features", "home", 1000)
    pages = {"pages/src_01-features-home.md": HOME, "pages/src_01-features-home.raw.md": HOME}
    res, _ = run([ok(nova())], crawl([rec]), pages)
    assert isinstance(res, ExtractResult)
    assert not [w for w in res.warnings if w.startswith("section_not_covered")]
    res, _ = run(
        [ok(nova())], crawl([rec]), pages, ExtractSettings(coverage_page_types=("features",))
    )
    assert isinstance(res, ExtractResult)
    assert [w for w in res.warnings if w.startswith("section_not_covered")]


# ---------------------------------------------------------------- số liệu tự công bố
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5.06M+ AI content views", True),
        ("33,973+ new followers", True),
        ("1.3M+ unique reach on Facebook", True),
        ("+35% more opportunities handled per week", True),
        ("5x content output", True),
        ("Save 12 hours / month", True),
        ("40% reduction in hiring time", True),
        ("1,867 elite members", True),
        ("35k+ followers", True),
        ("$9 per month", False),  # giá thuộc pricing
        ("Pro 10 seats", False),
        ("Close deals faster with AI", False),
        ("Step 2 of 3", False),
        ("Learn in 5-minute lessons", False),
    ],
)
def test_has_metric(text: str, expected: bool) -> None:
    assert has_metric(text) is expected


def test_metric_warnings_chi_usp_va_use_case() -> None:
    pkb = {
        "usp": [
            fact("src_01", "5.06M+ AI content views", text="Theo Nova công bố: 5.06M+ lượt xem"),
            fact("src_01", "Verifiable certificates", text="Chứng chỉ xác thực"),
        ],
        "use_cases": [fact("src_01", SALES, title="Sales"), fact("src_01", "Hi", title="HR")],
        "features": [fact("src_01", "90+ tools", name="Tools")],
    }
    assert metric_warnings(pkb) == [
        "self_reported_metric:usp[0]",
        "self_reported_metric:use_cases[0]",
    ]


def test_extract_them_warning_so_lieu_tu_cong_bo() -> None:
    data = nova()
    data["usp"] = [fact("src_01", "35k+ followers, average 36k views per video", text="x")]
    res = run_nova(data)
    assert "self_reported_metric:usp[0]" in res.warnings


# ---------------------------------------------------------------- audiences, usp
def test_audiences_va_usp_vao_pkb_v03_hop_le_va_duoc_kiem_evidence() -> None:
    data = nova()
    data["audiences"] = [
        fact("src_01", INTRO, segment="Small businesses", jtbd="Build smarter teams"),
        fact("src_01", JOBS, segment="Job seekers"),
        fact("src_01", JOBS, segment="Job seekers"),  # trùng segment: bỏ
    ]
    data["usp"] = [fact("src_01", "not on the page", text="Theo Nova công bố: 1M+ views")]
    res = run_nova(data)
    assert [a["segment"] for a in res.data["audiences"]] == ["Small businesses", "Job seekers"]
    assert res.data["audiences"][0]["jtbd"] == "Build smarter teams"
    assert res.data["usp"][0]["text"].startswith("Theo Nova công bố:")
    assert "evidence_not_found:usp[0]" in res.warnings  # evidence của usp cũng bị kiểm
    assert len(list(iter_facts(res.data))) == res.facts
    validate_pkb(res.data, res.sources)


def test_khong_audiences_usp_thi_pkb_van_hop_le() -> None:
    res = run_nova(nova())
    assert (res.data["audiences"], res.data["usp"]) == ([], [])
    validate_pkb(res.data, res.sources)


def test_schema_gui_llm_co_audiences_va_usp_con_pkb_v03_khong_doi() -> None:
    props = PKBExtract.model_json_schema()["properties"]
    assert {"audiences", "usp"} <= set(props)
    from worker.m1.pkb.models import PKB_SCHEMA_VERSION

    assert PKB_SCHEMA_VERSION == "0.3"


def test_prompt_huong_dan_dung_truong_cua_v03() -> None:
    for needle in ("use_cases: tối đa 12", "audiences", "usp:", "Theo <tên sản phẩm> công bố:"):
        assert needle in SYSTEM_PROMPT
    assert "KHÔNG ghi vào trường nào" in SYSTEM_PROMPT  # số liệu thị trường
    assert "0,00M+" in SYSTEM_PROMPT  # bộ đếm số chưa chạy (crawl AISoEasy 29/10)


# ---------------------------------------------------------------- số đi với nhãn
TRACTION = (
    "5.06M+\n    AI content views 33,973+\n    new followers 1.3M+\n    unique reach on Facebook"
)
USP0_EVIDENCE = "AI content views 33,973+\n    new followers 1.3M+\n    unique reach on Facebook"
USP0_TEXT = (
    "Theo AI So Easy công bố: 33,973+ AI content views, 1.3M+ new followers, "
    "1.3M+ unique reach on Facebook"
)


def test_ca_usp0_aisoeasy_ghep_lech_mot_nac_thi_bao_metric_label_mismatch() -> None:
    assert label_mismatch(USP0_TEXT, USP0_EVIDENCE)
    pkb = {"usp": [fact("src_01", USP0_EVIDENCE, text=USP0_TEXT)]}
    assert metric_warnings(pkb) == [
        "self_reported_metric:usp[0]",
        "metric_label_mismatch:usp[0]",
    ]


@pytest.mark.parametrize(
    ("text", "evidence"),
    [
        # ghép đúng: số đứng trước nhãn, kể cả xuống dòng
        (
            "Theo AI So Easy công bố: 5.06M+ AI content views, 33,973+ new followers, "
            "1.3M+ unique reach on Facebook",
            TRACTION,
        ),
        # usp[1]..usp[4] của lần chạy thật 30/10
        (
            "Theo AI So Easy công bố: 2.58M+ Views, 35k+ followers, avg 36k views/video on TikTok",
            "### TikTok\nThe Virality Engine\n2.58M+ Views\n35k+ followers, avg 36k views/video",
        ),
        (
            "Theo AI So Easy công bố: 56.3% of Short views come from Active Search",
            "### YouTube\nThe Evergreen Search\n56.3%\nof Short views come from Active Search",
        ),
        (
            "Theo AI So Easy công bố: 1,867+ elite members, +720 in H1 in Facebook Group",
            "### Facebook Group\nThe Advocate Cult\n1,867+\nelite members, +720 in H1",
        ),
        # LLM dịch nhãn sang tiếng Việt: evidence không có từ nhãn, không phán đoán
        ("Theo Acme công bố: 2M+ lượt tải", "2M+ downloads in 2025"),
        # số không có trong evidence: việc của evidence_not_found / value_not_in_evidence
        ("Theo Acme công bố: 3M+ views", "2M+ views"),
        # số ở cuối câu, không có nhãn theo sau
        ("Theo Acme công bố: người dùng tăng 40%", "Users grew 40%"),
    ],
)
def test_so_di_dung_nhan_thi_khong_bao(text: str, evidence: str) -> None:
    assert not label_mismatch(text, evidence)


def test_use_case_title_khong_so_thi_khong_kiem_nhan() -> None:
    pkb = {"use_cases": [fact("src_01", SALES, title="Sales: Close deals faster with AI")]}
    assert metric_warnings(pkb) == ["self_reported_metric:use_cases[0]"]


def test_prompt_dan_cap_so_nhan_va_cac_khoi_con_thieu() -> None:
    for needle in ("Challenge", "chương trình đối tác", "nhân viên theo phòng ban", "NGAY SAU"):
        assert needle in SYSTEM_PROMPT
