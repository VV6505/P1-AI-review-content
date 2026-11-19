"""M2 P1-AC-03: `generate_script(input, llm)` sinh kịch bản tiếng Việt từ PKB đã xác nhận.

Luồng (bàn giao 11/11 của #83, `8008cbf`): kiểm input (không gọi LLM nếu sai) → lời gọi sinh
→ **chuẩn bị `visual_plan.kind`** từ allowlist (chỉ `kind`, có audit; output thô giữ nguyên)
→ schema + content validator của Định (không nới luật)
→ nếu còn lỗi validator, lỗi QA cụ thể hoặc khuyến nghị âm tiết ngoài 150–170: **đúng 1 lời
  gọi sửa** theo template sửa; bản sửa cũng qua chuẩn bị kind + validator → thêm
  `estimated_duration_s`.
Không có lượt sửa thứ hai. Lỗi trả trong `ScriptResult`, không raise. Mọi tầng (thô, sau chuẩn bị
kind, feedback, bản sửa, kết quả kiểm) nằm trong `ScriptResult.stages`; chi phí từng lời gọi là
một item riêng trong `cost_breakdown` (`generate_script`, `generate_script_repair`).

CLI chạy tay: `uv run python -m worker.m2.generate <input.json> --out <thư mục> [--no-repair]
[--qa-feedback qa.json]`. Ghi `script.json` (kịch bản cuối, hoặc bản chuẩn bị/thô khi không hợp
lệ), `stages.json`, `initial.raw.json`, `initial.prepared.json`, `repair.raw.json`,
`repair.prepared.json`, `feedback.json`, `validation.json`, `cost.json`. Gọi Gemini thật cần
`GEMINI_API_KEY`; `LLM_PROVIDER=fixture` thì không gọi mạng.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from worker.m1.llm import LLM, CostBreakdown, CostItem, LLMError, LLMErrorCode, make_llm
from worker.m2.kind import allowlist_errors, allowlist_revision, prepare_kinds
from worker.m2.prompt import build_system_prompt, build_user_prompt
from worker.m2.repair import (
    SYLLABLE_RANGE,
    build_repair_prompt,
    build_repair_user_prompt,
    syllable_feedback,
    validator_feedback,
)
from worker.m2.schema import WORKER_FIELDS, gemini_response_schema
from worker.m2.validate import SCRIPT_SCHEMA, content_errors, schema_errors, validate_input

STEP = "generate_script"
REPAIR_STEP = "generate_script_repair"
TARGET_RANGE_S = (15, 59)  # pilot short video: nội dung quyết định độ dài, đầu ra phải dưới 60s
_SYLLABLE_RE = re.compile(r"\w+")


class M2Settings(BaseModel):
    # Tốc độ đọc giả định để ước tính thời lượng. 3.75 là mức khởi điểm của Định; VieNeu đo thử
    # 3,6–3,9 âm tiết/giây (#73). Hiệu chỉnh lại theo TTS thật.
    syllables_per_s: float = 3.75
    narration_min_syllables: int = SYLLABLE_RANGE[0]
    narration_max_syllables: int = SYLLABLE_RANGE[1]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> M2Settings:
        env = os.environ if env is None else env
        values: dict[str, Any] = {}
        if raw := env.get("M2_SYLLABLES_PER_S"):
            values["syllables_per_s"] = float(raw)
        if raw := env.get("M2_NARRATION_MIN_SYLLABLES"):
            values["narration_min_syllables"] = int(raw)
        if raw := env.get("M2_NARRATION_MAX_SYLLABLES"):
            values["narration_max_syllables"] = int(raw)
        settings = cls(**values)
        if settings.narration_min_syllables > settings.narration_max_syllables:
            raise ValueError("M2_NARRATION_MIN_SYLLABLES phải nhỏ hơn hoặc bằng MAX")
        return settings


class M2ErrorCode(StrEnum):
    INPUT_INVALID = "m2_input_invalid"  # input/PKB sai: không gọi LLM, không retry


@dataclass
class ScriptResult:
    status: Literal["completed", "failed"]
    data: dict[str, Any] | None  # kịch bản hợp lệ (đã có estimated_duration_s); None nếu lỗi
    cost_breakdown: dict[str, Any]  # cost_breakdown v1, gồm mọi lần gọi kể cả lần lỗi
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None  # LLMErrorCode hoặc M2ErrorCode
    error_message: str | None = None
    retryable: bool = False
    retry_after: datetime | None = None
    errors: list[str] = field(default_factory=list)  # lỗi validator (input hoặc output)
    raw_output: dict[str, Any] | None = None  # JSON thô của LLM khi không hợp lệ, để rà
    stages: dict[str, Any] = field(default_factory=dict)  # thô → chuẩn bị kind → feedback → sửa


def count_syllables(text: str) -> int:
    """Âm tiết = cụm chữ/số liền nhau. Tiếng Việt viết tách âm tiết bằng khoảng trắng nên khá sát.

    Đếm thiếu khi TTS đọc dài hơn chữ viết: số ("100" = 1, đọc "một trăm"), đơn vị ("500MB"),
    từ tiếng Anh ("DOCX"), URL. Chỉ là ước tính.
    """
    return len(_SYLLABLE_RE.findall(text))


def narration_syllables(script: dict[str, Any]) -> int:
    return sum(
        count_syllables(seg["text"])
        for scene in script["scenes"]
        for seg in scene["narration_segments"]
    )


def _failed(
    code: str,
    message: str,
    items: list[CostItem],
    *,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    raw: dict[str, Any] | None = None,
    retryable: bool = False,
    retry_after: datetime | None = None,
    stages: dict[str, Any] | None = None,
) -> ScriptResult:
    return ScriptResult(
        status="failed",
        data=None,
        cost_breakdown=CostBreakdown(items=items).dump(),
        warnings=list(warnings or []),
        error_code=code,
        error_message=message,
        retryable=retryable,
        retry_after=retry_after,
        errors=list(errors or []),
        raw_output=raw,
        stages=stages or {},
    )


@dataclass
class _Attempt:
    """Một lần sinh: raw (nguyên văn model) → bản chuẩn bị kind → kết quả kiểm."""

    raw: dict[str, Any]
    prepared: dict[str, Any]
    kind_audit: list[dict[str, Any]]
    schema_errors: list[str]
    content_errors: list[str]
    warnings: list[str]
    syllables: int | None  # chỉ tính được khi qua schema

    @property
    def errors(self) -> list[str]:
        return self.schema_errors + self.content_errors

    @property
    def valid(self) -> bool:
        return not self.errors

    def stage(self) -> dict[str, Any]:
        return {
            "kind_audit": self.kind_audit,
            "schema_errors": self.schema_errors,
            "content_errors": self.content_errors,
            "syllables": self.syllables,
            "valid": self.valid,
        }


def _evaluate(raw: dict[str, Any], inp: dict[str, Any]) -> _Attempt:
    warnings: list[str] = []
    script = dict(raw)
    for name in WORKER_FIELDS:  # trường của worker: model tự điền thì bỏ, worker tính lại
        if name in script:
            script.pop(name)
            warnings.append(f"llm_filled_worker_field:{name}")
    prepared, audit = prepare_kinds(script, inp)  # chỉ `kind`; raw giữ nguyên
    schema = schema_errors(SCRIPT_SCHEMA, prepared)
    content = [] if schema else content_errors(prepared, inp)
    syllables = None if schema else narration_syllables(prepared)
    return _Attempt(raw, prepared, audit, schema, content, warnings, syllables)


def _feedback(
    att: _Attempt,
    qa: list[dict[str, Any]],
    target_range: tuple[int, int] = SYLLABLE_RANGE,
) -> list[dict[str, Any]]:
    fb = validator_feedback(att.schema_errors, att.content_errors)
    if att.syllables is not None:
        fb += syllable_feedback(att.syllables, target_range)
    return fb + list(qa)


def _stages_doc(inp: dict[str, Any]) -> dict[str, Any]:
    return {"allowlist_revision": allowlist_revision(inp)}


async def generate_script(
    inp: dict[str, Any],
    llm: LLM,
    *,
    settings: M2Settings | None = None,
    qa_feedback: list[dict[str, Any]] | None = None,
    repair: bool = True,
) -> ScriptResult:
    """`inp` theo `p1-ac-03-input.v1`. BE cần `await`.

    Tối đa 2 lời gọi: sinh + (nếu còn feedback) một lượt sửa. `qa_feedback` là lỗi QA do người/QA
    cung cấp (`{"source": "qa", "message": ..., "scene_id"?...}`), không do worker tự sinh.
    """
    settings = settings or M2Settings.from_env()
    narration_range = (
        settings.narration_min_syllables,
        settings.narration_max_syllables,
    )
    qa = [{**f, "source": "qa"} for f in (qa_feedback or [])]
    input_errors = validate_input(inp) or allowlist_errors(inp)
    if input_errors:
        return _failed(M2ErrorCode.INPUT_INVALID, "input không hợp lệ", [], errors=input_errors)
    stages = _stages_doc(inp)

    try:
        res = await llm.generate_json(
            step=STEP,
            system=build_system_prompt(inp, narration_range),
            prompt=build_user_prompt(inp),
            response_schema=gemini_response_schema(),
        )
    except LLMError as e:
        return _failed(
            e.code, e.message, e.cost_items, retryable=e.retryable, retry_after=e.retry_after,
            stages=stages,
        )  # fmt: skip

    items = list(res.cost_items)
    first = _evaluate(res.data, inp)
    stages["initial"] = {"raw": first.raw, "prepared": first.prepared, **first.stage()}
    final = first
    warnings = list(first.warnings)
    feedback = _feedback(first, qa, narration_range)
    stages["feedback"] = feedback

    if feedback and repair:
        try:
            fixed = await llm.generate_json(
                step=REPAIR_STEP,
                system=build_repair_prompt(
                    inp, first.prepared, feedback, narration_range
                ),
                prompt=build_repair_user_prompt(),
                response_schema=gemini_response_schema(),
            )
        except LLMError as e:
            items += e.cost_items
            stages["repair_error"] = {"code": str(e.code), "message": e.message}
            if first.valid and not qa:  # chỉ còn khuyến nghị âm tiết: giữ bản đã qua kiểm
                warnings.append(f"repair_failed_keep_candidate:{e.code}")
            else:
                return _failed(
                    e.code, e.message, items, errors=first.errors, warnings=warnings,
                    raw=first.raw, retryable=e.retryable, retry_after=e.retry_after, stages=stages,
                )  # fmt: skip
        else:
            items += fixed.cost_items
            second = _evaluate(fixed.data, inp)
            stages["repair"] = {"raw": second.raw, "prepared": second.prepared, **second.stage()}
            warnings += [f"repair:{w}" for w in second.warnings]
            if second.valid:
                final = second
            elif first.valid and not qa:  # bản sửa hỏng, bản đầu vẫn qua kiểm: không đổi
                warnings.append(f"repair_rejected_keep_candidate:{len(second.errors)} lỗi")
            else:
                return _failed(
                    LLMErrorCode.INVALID_OUTPUT,
                    f"output sau lượt sửa không qua validator ({len(second.errors)} lỗi)",
                    items, errors=second.errors, warnings=warnings, raw=second.raw, stages=stages,
                )  # fmt: skip
    elif not first.valid:
        return _failed(
            LLMErrorCode.INVALID_OUTPUT,
            f"output không qua validator ({len(first.errors)} lỗi)",
            items, errors=first.errors, warnings=warnings, raw=first.raw, stages=stages,
        )  # fmt: skip

    script = dict(final.prepared)
    syllables = narration_syllables(script)
    slow, shigh = narration_range
    range_is_local_override = narration_range != SYLLABLE_RANGE
    minimum_acceptable = max(80, round(slow * 0.82))
    outside_hard_limit = syllables > shigh or syllables < minimum_acceptable
    if range_is_local_override and outside_hard_limit:
        return _failed(
            LLMErrorCode.INVALID_OUTPUT,
            (
                f"lời đọc {syllables} âm tiết, ngoài vùng tự điều chỉnh "
                f"{minimum_acceptable}–{shigh} (mục tiêu {slow}–{shigh})"
            ),
            items,
            errors=[
                f"narration_segments: cần tối thiểu {minimum_acceptable} và tối đa "
                f"{shigh} âm tiết, nhận {syllables}"
            ],
            warnings=warnings,
            raw=final.raw,
            stages=stages,
        )
    if range_is_local_override and syllables < slow:
        warnings.append(
            f"narration_short_but_renderable:{syllables}; renderer giữ thời lượng tự nhiên"
        )
    estimate = round(syllables / settings.syllables_per_s, 1)
    script["estimated_duration_s"] = estimate
    warnings.append(
        f"estimated_duration_s_is_estimate:{syllables} âm tiết / {settings.syllables_per_s} "
        "âm tiết/s; không phải duration TTS hay MP4"
    )
    low, high = TARGET_RANGE_S
    if not low <= estimate <= high:
        warnings.append(f"estimate_outside_target:{estimate}s ngoài {low}–{high}s")
    final_errors = schema_errors(SCRIPT_SCHEMA, script)  # estimate phải hợp lệ schema của Định
    if final_errors:
        return _failed(
            LLMErrorCode.INVALID_OUTPUT, "estimated_duration_s ngoài schema", items,
            errors=final_errors, warnings=warnings, raw=final.raw, stages=stages,
        )  # fmt: skip
    stages["final"] = {"from": "repair" if final is not first else "initial"}
    return ScriptResult(
        status="completed",
        data=script,
        cost_breakdown=CostBreakdown(items=items).dump(),
        warnings=warnings,
        stages=stages,
    )


# ---------------------------------------------------------------- CLI


def load_env(path: Path) -> None:
    """Đọc KEY=VALUE từ .env vào os.environ (không ghi đè biến đã có). Như CLI extract của M1."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _write(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(res: ScriptResult) -> None:
    items = res.cost_breakdown["items"]
    tok_in = sum(i["tokens_in"] for i in items)
    tok_out = sum(i["tokens_out"] for i in items)
    cost = sum(i["cost_usd"] for i in items)
    print(f"status={res.status} llm_calls={len(items)} tokens_in={tok_in} tokens_out={tok_out} "
          f"cost_usd(giá niêm yết)={cost:.6f}")  # fmt: skip
    for i in items:
        print(f"  call {i.get('step')} attempt={i['attempt']}: in={i['tokens_in']} "
              f"out={i['tokens_out']} cost_usd={i['cost_usd']:.6f}")  # fmt: skip
    for name in ("initial", "repair"):
        st = res.stages.get(name)
        if st:
            n_err = len(st["schema_errors"]) + len(st["content_errors"])
            changed = [a for a in st["kind_audit"] if a["status"] in ("filled", "replaced")]
            print(f"  [{name}] valid={st['valid']} errors={n_err} syllables={st['syllables']} "
                  f"kind_changed={len(changed)}")  # fmt: skip
    if res.data:
        scenes = res.data["scenes"]
        segs = sum(len(s["narration_segments"]) for s in scenes)
        claims = sum(len(s["claims"]) for s in scenes)
        print(f"scenes={len(scenes)} segments={segs} claims={claims} "
              f"estimated_duration_s={res.data['estimated_duration_s']}")  # fmt: skip
    if res.error_code:
        print(f"!! {res.error_code}: {res.error_message} (retryable={res.retryable})")
    for e in res.errors:
        print(f"  error: {e}")
    for w in res.warnings:
        print(f"  warning: {w}")


async def _main(args: argparse.Namespace) -> int:
    out = Path(args.out)
    inp = json.loads(Path(args.input).read_text(encoding="utf-8"))
    inp.pop("_note", None)  # ghi chú cho người đọc, không thuộc contract input
    llm = make_llm()
    qa = json.loads(Path(args.qa_feedback).read_text(encoding="utf-8")) if args.qa_feedback else []
    res = await generate_script(inp, llm, qa_feedback=qa, repair=not args.no_repair)
    script = res.data if res.data is not None else res.raw_output
    if script is not None:
        _write(out / "script.json", script)
    _write(out / "stages.json", res.stages)
    _write(out / "feedback.json", res.stages.get("feedback", []))
    for name in ("initial", "repair"):
        st = res.stages.get(name)
        if st:
            _write(out / f"{name}.raw.json", st["raw"])
            _write(out / f"{name}.prepared.json", st["prepared"])
            _write(out / f"{name}.kind_audit.json", st["kind_audit"])
    retry_after = res.retry_after.isoformat() if res.retry_after else None
    _write(out / "validation.json", {
        "status": res.status, "model": llm.model, "error_code": res.error_code,
        "error_message": res.error_message, "retryable": res.retryable,
        "retry_after": retry_after, "errors": res.errors, "warnings": res.warnings,
        "script_is_raw_output": res.data is None and script is not None,
    })  # fmt: skip
    _write(out / "cost.json", res.cost_breakdown)
    _summary(res)
    return 0 if res.status == "completed" else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m worker.m2.generate", description=__doc__)
    parser.add_argument("input", help="File input p1-ac-03-input.v1 (JSON)")
    parser.add_argument("--out", required=True, help="Thư mục ghi kết quả")
    parser.add_argument("--env", default=".env", help="File .env (mặc định ./.env)")
    parser.add_argument(
        "--no-repair", action="store_true", help="Không gọi lượt sửa (chỉ 1 lời gọi)"
    )
    parser.add_argument(
        "--qa-feedback", help="JSON danh sách lỗi QA cụ thể (nguồn 'qa') cho lượt sửa"
    )
    args = parser.parse_args()
    load_env(Path(args.env))
    Path(args.out).mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Windows cp1252
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
