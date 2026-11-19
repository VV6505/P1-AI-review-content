"""Bước 1.4 cho product `software`: kết quả crawl → PKB v0.3 (`data` + `sources`), 1 lời gọi LLM.

Luồng: chọn top-k trang → 1 lời gọi structured output → sửa evidence quá dài → validate theo schema
gửi LLM → bỏ fact trỏ tới trang lạ → kiểm evidence (không khớp: giữ fact, thêm warning) → gộp, bỏ
trùng → conflicts → điền trường do code làm → validate PKB v0.3.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from worker.m1.extract.context import add_block_context
from worker.m1.extract.coverage import coverage_warnings
from worker.m1.extract.evidence import (
    EvidenceIndex,
    free_only,
    has_word,
    iter_facts,
    metric_warnings,
    name_candidates,
    norm,
    repair_evidence,
    value_warnings,
)
from worker.m1.extract.merge import merge, price_conflicts
from worker.m1.extract.pages import PageReader, SourceDoc, iter_all_docs, select_docs
from worker.m1.extract.plans import fix_plans
from worker.m1.extract.prompt import SYSTEM_PROMPT, build_prompt
from worker.m1.extract.schema import PKBExtract
from worker.m1.llm import LLM, CostBreakdown, CostItem, LLMError, LLMErrorCode
from worker.m1.models import CrawlResult
from worker.m1.pkb.models import PKB_SCHEMA_VERSION
from worker.m1.pkb.validate import PKBInvalid, validate_pkb

STEP = "extract"


class ExtractSettings(BaseModel):
    top_pages: int = 10  # mode batch của spike: gom N trang điểm cao nhất vào 1 lời gọi
    raw_page_types: tuple[str, ...] = ("pricing",)  # fit_markdown làm rơi thẻ giá
    # Độ phủ section chỉ kiểm ở trang giới thiệu (trang chủ, about: `other`). Trang features /
    # docs / faq / pricing có hàng chục section lặp dạng, PKB chỉ lấy vài mục nên bỏ là có chủ ý.
    coverage_page_types: tuple[str, ...] = ("other",)


class ExtractErrorCode(StrEnum):
    NO_PAGES = "extract_no_pages"  # crawl failed hoặc không còn trang nào đọc được
    PKB_INVALID = "pkb_invalid"  # PKB sau khi ghép không hợp lệ v0.3 (lỗi code, không retry)


class ExtractError(Exception):
    """Lỗi của bước extract. Mã lấy từ `LLMErrorCode` hoặc `ExtractErrorCode`.

    Luôn kèm `cost_breakdown` (v1) của các lần gọi đã làm, để job lỗi vẫn ghi được chi phí.
    """

    def __init__(
        self,
        code: LLMErrorCode | ExtractErrorCode,
        detail: str = "",
        *,
        retryable: bool = False,
        retry_after: datetime | None = None,
        cost_items: list[CostItem] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.retry_after = retry_after
        self.cost_breakdown = CostBreakdown(items=list(cost_items or [])).dump()
        self.warnings = list(warnings or [])

    @property
    def message(self) -> str:
        return str(self)


@dataclass
class ExtractResult:
    data: dict[str, Any]  # cột product_knowledge.data (PKB v0.3)
    sources: list[dict[str, Any]]  # cột product_knowledge.sources
    cost_breakdown: dict[str, Any]  # cost_breakdown v1
    warnings: list[str] = field(default_factory=list)
    evidence_in_source: float = 0.0  # tỉ lệ fact có evidence nguyên văn trong trang nguồn
    facts: int = 0


def _product_name(crawl: CrawlResult) -> str:
    return urlsplit(crawl.root_url).netloc or crawl.root_url


def _drop_unknown_sources(data: dict[str, Any], index: EvidenceIndex) -> list[str]:
    """Bỏ fact có `source_id` không thuộc trang đã gửi. Trả warnings."""
    warnings: list[str] = []
    bad = [(p, f) for p, f in iter_facts(data) if not index.known(f.get("source_id"))]
    if not bad:
        return warnings
    bad_ids = {id(f) for _, f in bad}

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: (None if isinstance(v, dict) and id(v) in bad_ids else strip(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [strip(v) for v in node if not (isinstance(v, dict) and id(v) in bad_ids)]
        return node

    cleaned = strip(data)
    data.clear()
    data.update(cleaned)
    warnings += [f"unknown_source_id:{p}:{f.get('source_id')}" for p, f in bad]
    return warnings


def _check_evidence(data: dict[str, Any], index: EvidenceIndex) -> tuple[list[str], float, int]:
    """Fact có evidence không khớp nguồn: giữ fact, thêm warning (quyết định đã duyệt)."""
    facts = list(iter_facts(data))
    missing = [p for p, f in facts if not index.found(f.get("source_id"), f.get("evidence"))]
    ratio = round(1 - len(missing) / len(facts), 3) if facts else 0.0
    return [f"evidence_not_found:{p}" for p in missing], ratio, len(facts)


_FACT_SUFFIX = re.compile(r"\.(?:value|evidence|source_id)$")
_LEAF_VALUE = re.compile(
    r"^specs\[\d+\]\.value$"
)  # physical: `value` là dữ liệu, không phải vỏ fact


def _fact_path(field: str) -> str:
    """Bỏ hậu tố `.value` / `.evidence` / `.source_id` để trỏ vào node fact (thống nhất ở #83)."""
    while not _LEAF_VALUE.match(field) and (m := _FACT_SUFFIX.search(field)):
        field = field[: m.start()]
    return field


def _node(data: Any, path: str) -> tuple[bool, Any]:
    node = data
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if tok.startswith("["):
            i = int(tok[1:-1])
            if not isinstance(node, list) or i >= len(node):
                return False, None
            node = node[i]
        elif isinstance(node, dict) and tok in node:
            node = node[tok]
        else:
            return False, None
    return path != "", node


def _is_broad(pkb: dict[str, Any], field: str) -> bool:
    """Path trỏ tới cả mảng (`features`) hoặc cả nhóm (`pricing`), không phải 1 fact."""
    ok, node = _node(pkb, field)
    return ok and (isinstance(node, list) or (isinstance(node, dict) and "source_id" not in node))


def _narrow(pkb: dict[str, Any], claims: list[dict[str, Any]]) -> str | None:
    """Fact duy nhất của PKB mà các claim nói tới (cùng `source_id`, evidence chồng lên nhau
    hoặc giá trị claim nằm trong evidence của fact). Không có hoặc nhiều hơn 1 thì None."""
    paths: set[str] = set()
    for cl in claims:
        ev, val = norm(cl.get("evidence") or ""), norm(cl.get("value") or "")
        for path, f in iter_facts(pkb):
            fe = norm(f.get("evidence") or "")
            if (
                f.get("source_id") == cl["source_id"]
                and fe
                and ((ev and (ev in fe or fe in ev)) or (val and val in fe))
            ):
                paths.add(path)
    return paths.pop() if len(paths) == 1 else None


def _llm_conflicts(
    raw: list[dict[str, Any]], index: EvidenceIndex, pkb: dict[str, Any]
) -> tuple[list[dict], list[str]]:
    """Đổi conflicts của LLM sang dạng PKB. Bỏ claim trỏ tới trang lạ; còn < 2 giá trị khác nhau
    thì không phải mâu thuẫn. Evidence của claim không khớp: giữ, thêm warning. `field` được
    chuẩn hoá về node fact; field cả mảng thì thu hẹp về fact mà claim nói tới, không được thì
    giữ và cảnh báo `conflict_too_broad`."""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for i, c in enumerate(raw):
        claims = [cl for cl in c.get("claims") or [] if index.known(cl.get("source_id"))]
        for j, cl in enumerate(claims):
            if not index.found(cl["source_id"], cl.get("evidence")):
                warnings.append(f"evidence_not_found:conflicts[{i}].claims[{j}]")
        if len({cl["value"].strip() for cl in claims}) < 2:
            continue
        field = _fact_path(c.get("field") or "unknown")
        if _is_broad(pkb, field):
            if narrowed := _narrow(pkb, claims):
                field = narrowed
            else:
                warnings.append(f"conflict_too_broad:{field}")
        out.append(
            {
                "field": field,
                "values": [cl["value"] for cl in claims],
                "source_ids": [cl["source_id"] for cl in claims],
            }
        )
    return out, warnings


def _resolves(data: Any, path: str) -> bool:
    """`identity.description`, `pricing.plans[0].list_price` có trỏ tới giá trị trong PKB không."""
    ok, node = _node(data, path)
    return ok and node is not None


def _price_warnings(pkb: dict[str, Any]) -> list[str]:
    """Giá khuyến mãi cao hơn giá niêm yết: LLM thường đảo 2 trường. Chỉ cảnh báo, không tự đảo
    (đảo là đoán); người dùng sửa ở bước xác nhận."""
    out = []
    for i, p in enumerate(pkb["pricing"].get("plans") or []):
        lp, pp = p.get("list_price"), p.get("promo_price")
        if isinstance(lp, int | float) and isinstance(pp, int | float) and pp > lp:
            out.append(f"promo_above_list:pricing.plans[{i}]")
    plans = pkb["pricing"].get("plans") or []
    if free_only(plans):
        # Plan không có trường ghi chú (không đổi schema v0.3): cờ nằm ở warning để FE / M2 không
        # đọc month / monthly của plan Free như cam kết chu kỳ thanh toán.
        out.append("free_only_placeholder_period:pricing.plans[0]")
    return out


def _fix_name_evidence(
    pkb: dict[str, Any], docs: list[SourceDoc], all_docs: Iterator[SourceDoc], index: EvidenceIndex
) -> None:
    """Evidence của `identity.name` không chứa tên: tìm tên trong og:site_name, <title>, h1 của
    các trang đã crawl (trang đã gửi trước). Thấy thì thay evidence + `source_id`, không đổi
    `value`; trang chưa gửi được thêm vào `sources`. Không thấy thì để `value_not_in_evidence`."""
    name = pkb["identity"]["name"]
    value = name.get("value")
    if not isinstance(value, str) or has_word(value, name.get("evidence") or ""):
        return
    for doc in all_docs:
        for text, via in name_candidates(doc.meta, doc.text):
            if has_word(value, text):
                name.update(source_id=doc.source_id, evidence=text)
                if via:
                    name["extracted_via"] = via
                if doc.source_id not in {d.source_id for d in docs}:
                    docs.append(doc)
                    index.add(doc.source_id, doc.index_text)
                return


def _assemble(data: dict[str, Any], crawl: CrawlResult, region: str, locale: str) -> dict:
    """Điền các trường do code làm (không phải LLM) và nâng lên v0.3 `software`."""
    identity = {**data["identity"], "website": crawl.root_url, "product_kind": "software"}
    pricing = {**data["pricing"], "region": region, "locale": locale}
    features = [{**f, "id": f"f{i}"} for i, f in enumerate(data.get("features") or [], 1)]
    return {
        "schema_version": PKB_SCHEMA_VERSION,
        "identity": identity,
        "pricing": pricing,
        "features": features,
        "use_cases": data.get("use_cases") or [],
        "limitations": data.get("limitations") or [],
        "audiences": data.get("audiences") or [],
        "usp": data.get("usp") or [],
    }


async def extract_product(
    crawl_result: CrawlResult,
    page_store: PageReader,
    llm: LLM,
    *,
    settings: ExtractSettings | None = None,
) -> ExtractResult:
    """Kết quả crawl → PKB v0.3. Lỗi → `ExtractError` (kèm `cost_breakdown` và `retry_after`)."""
    s = settings or ExtractSettings()
    if crawl_result.status != "completed":
        raise ExtractError(ExtractErrorCode.NO_PAGES, f"crawl {crawl_result.status}")
    docs, warnings = select_docs(crawl_result, page_store, s.top_pages, s.raw_page_types)
    if not docs:
        raise ExtractError(ExtractErrorCode.NO_PAGES, "không có trang đọc được", warnings=warnings)
    sent_ids = {d.source_id for d in docs}  # `docs` có thể thêm trang tên sản phẩm (chưa gửi LLM)

    try:
        res = await llm.generate_json(
            step=STEP,
            system=SYSTEM_PROMPT,
            prompt=build_prompt(_product_name(crawl_result), docs),
            response_schema=PKBExtract.model_json_schema(),
        )
    except LLMError as e:
        raise ExtractError(
            e.code,
            e.detail,
            retryable=e.retryable,
            retry_after=e.retry_after,
            cost_items=e.cost_items,
            warnings=warnings,
        ) from e
    items = res.cost_items
    if res.attempts > 1:
        warnings.append(f"llm_retried:{res.attempts - 1}:wait_{res.wait_seconds:g}s")

    data = res.data
    if n := repair_evidence(data):
        warnings.append(f"evidence_truncated:{n}")
    try:
        PKBExtract.model_validate(data)
    except ValidationError as e:
        raise ExtractError(
            LLMErrorCode.INVALID_OUTPUT,
            f"schema: {str(e)[:500]}",
            cost_items=items,
            warnings=warnings,
        ) from e

    index = EvidenceIndex({d.source_id: d.index_text for d in docs})
    warnings += _drop_unknown_sources(data, index)
    if not isinstance((data.get("identity") or {}).get("name"), dict):
        raise ExtractError(
            LLMErrorCode.INVALID_OUTPUT,
            "identity.name trỏ tới trang không có trong nguồn",
            cost_items=items,
            warnings=warnings,
        )
    merged = merge([data])
    pkb = _assemble(merged, crawl_result, docs[0].region, docs[0].locale)
    _fix_name_evidence(
        pkb, docs, iter_all_docs(docs, crawl_result, page_store, s.raw_page_types), index
    )
    plan_warnings = fix_plans(pkb, docs)
    # Trước mọi bước kiểm evidence: evidence mới (nguyên văn) quyết định số liệu và độ phủ section
    plan_warnings += add_block_context(pkb, docs)
    ev_warnings, ratio, n_facts = _check_evidence(pkb, index)
    warnings += plan_warnings + ev_warnings + value_warnings(pkb) + _price_warnings(pkb)
    warnings += metric_warnings(pkb)
    checked = [d for d in docs if d.source_id in sent_ids and d.page_type in s.coverage_page_types]
    warnings += coverage_warnings(checked, pkb)
    conflicts, conflict_warnings = _llm_conflicts(merged["conflicts"], index, pkb)
    # field của LLM là chữ tự do: không trỏ tới trường nào thì cảnh báo (M2 đọc theo field_path)
    conflict_warnings += [
        f"conflict_field_unresolved:{c['field']}"
        for c in conflicts
        if not _resolves(pkb, c["field"])
    ]
    conflicts += price_conflicts(pkb)  # sau khi lọc và đánh id: chỉ số trong field trỏ đúng
    warnings += conflict_warnings
    if conflicts:
        pkb["quality"] = {"conflicts": conflicts}
        warnings += [f"conflict:{c['field']}" for c in conflicts]

    sources = [d.source() for d in docs]
    try:
        validate_pkb(pkb, sources)
    except PKBInvalid as e:
        raise ExtractError(
            ExtractErrorCode.PKB_INVALID, str(e), cost_items=items, warnings=warnings
        ) from e
    return ExtractResult(
        data=pkb,
        sources=sources,
        cost_breakdown=CostBreakdown(items=items).dump(),
        warnings=warnings,
        evidence_in_source=ratio,
        facts=n_facts,
    )
