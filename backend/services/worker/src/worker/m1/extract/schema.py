"""Schema structured output gửi cho LLM (bước 1.4, product `software`).

Giữ dạng v0.2 `PKBExtract` đã đo ở spike (identity dùng `TextFact`), thêm `conflicts`, và
`identity.name` đặt `value` trước `evidence` (`NameFact`, cùng dạng JSON). Code nâng kết
quả lên PKB v0.3 sau (service.py): `TextFact` v0.2 đọc được như `IdentityFact` `crawled`.
Không gửi Identity v0.3: `edited_by`, `previous`, `extracted_via` chỉ là nhiễu với LLM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from worker.m1.pkb.models import (
    EVIDENCE_MAX,
    SOURCE_ID_PATTERN,
    Fact,
    Feature,
    IdentityV02,
    Limitation,
    Pricing,
    UseCase,
)


class ConflictClaim(BaseModel):
    value: str = Field(description="Giá trị như trang ghi, vd. '90+ tools'.")
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    evidence: str = Field(min_length=1, max_length=EVIDENCE_MAX, description="Trích nguyên văn.")


class ExtractConflict(BaseModel):
    field: str = Field(
        description="Đường dẫn trường PKB liên quan, vd. 'identity.description', "
        "'pricing.plans', 'features'."
    )
    topic: str = Field(description="Thông tin bị ghi khác nhau, vd. 'số lượng công cụ'.")
    claims: list[ConflictClaim] = Field(description="Mỗi giá trị khác nhau kèm trang nguồn.")


class NameFact(BaseModel):
    """Như `TextFact` nhưng `value` đứng trước: LLM sinh JSON theo thứ tự khoá trong schema, nên
    viết tên trước rồi mới chọn evidence chứa tên. Thứ tự cũ (evidence trước) làm LLM lấy câu đầu
    trang, không có tên (chạy thật 21/10)."""

    value: str = Field(description="Tên sản phẩm.")
    origin: Literal["crawled"] = Field(description='Luôn là "crawled".')
    source_id: str = Field(pattern=SOURCE_ID_PATTERN, description="Id trang nguồn, vd. src_02.")
    evidence: str = Field(
        min_length=1,
        max_length=EVIDENCE_MAX,
        description="Đoạn trích NGUYÊN VĂN có đúng chữ tên sản phẩm, ≤ 200 ký tự.",
    )


class IdentityExtract(IdentityV02):
    name: NameFact  # pyright: ignore[reportIncompatibleVariableOverride]


class AudienceExtract(Fact):
    """Dạng gửi LLM của `audiences[]` v0.3 (`Audience`): luôn `crawled`, có nguồn và evidence."""

    segment: str = Field(description="Tên nhóm đối tượng, vd. 'SMEs', 'HR teams'.")
    jtbd: str | None = Field(
        default=None, description="Việc nhóm này muốn làm, chỉ khi trang nói rõ. Không thì null."
    )


class UspExtract(Fact):
    """Dạng gửi LLM của `usp[]` v0.3 (`Usp`). Số liệu tự công bố cũng vào đây."""

    text: str = Field(
        description="Điểm mạnh như trang ghi. Số liệu thành tích bắt đầu bằng "
        "'Theo <tên sản phẩm> công bố:'."
    )


class PKBExtract(BaseModel):
    """Phần LLM điền ở 1.4."""

    identity: IdentityExtract
    pricing: Pricing
    features: list[Feature] = Field(default_factory=list)
    use_cases: list[UseCase] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    audiences: list[AudienceExtract] = Field(default_factory=list)
    usp: list[UspExtract] = Field(default_factory=list)
    conflicts: list[ExtractConflict] = Field(default_factory=list)
