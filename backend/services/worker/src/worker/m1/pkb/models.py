"""PKB v0.3 (docs/specs/pkb/): model Pydantic để worker validate trước khi trả.

Port từ `spikes/m1-crawl-extract/schema.py` (v0.2) và `schema_v03.py` (v0.3). Spike vẫn là nơi xuất
`pkb-*.v0.3.schema.json`. Sửa luật ở đây thì sửa cả spike; test `test_pkb.py` chạy model này trên
`docs/specs/pkb/examples/` để bắt lệch giữa 2 nơi.

Không port: phần JSON Schema bổ sung (`JSON_RULES`, chỉ dùng khi xuất schema), lớp riêng của spike.
Luật tham chiếu chéo với `sources` (source_id có thật) nằm ở `validate.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

PKB_SCHEMA_VERSION = "0.3"
EVIDENCE_MAX = 200

SchemaVersion = Literal["0.2", "0.3"]  # v0.3 đọc được cả dữ liệu v0.2 (coi như software)
ProductKind = Literal["software", "physical"]
# `merchant` chỉ còn để đọc dữ liệu v0.2. Dữ liệu 0.3 phải dùng `owner`.
Origin = Literal["crawled", "owner", "inferred", "merchant"]
ItemOrigin = Literal["crawled", "owner"]
ExtractedVia = Literal["jsonld", "microdata", "og", "embedded", "dom"]
Availability = Literal["in_stock", "out_of_stock", "preorder", "unknown"]
ImageRole = Literal["hero", "gallery"]
PriceUnit = Literal["month", "year", "seat_month", "seat_year", "one_time"]
BillingCycle = Literal["monthly", "quarterly", "yearly", "one_time"]

SOURCE_ID_PATTERN = r"^src_\d{2}$"
VARIANT_ID_PATTERN = r"^v\d{1,3}$"
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)$"


# ---------------------------------------------------------------- fact (v0.2, giữ trong v0.3)
class Fact(BaseModel):
    origin: Literal["crawled"] = Field(description='Luôn là "crawled".')
    source_id: str = Field(pattern=SOURCE_ID_PATTERN, description="Id trang nguồn, vd. src_02.")
    evidence: str = Field(
        min_length=1,
        max_length=EVIDENCE_MAX,
        description="Câu trích NGUYÊN VĂN từ trang nguồn chứng minh fact, ≤ 200 ký tự.",
    )


class TextFact(Fact):
    value: str


class BoolFact(Fact):
    value: bool


class IntFact(Fact):
    value: int


class ModelVersion(Fact):
    name: str = Field(
        description="Tên model / phiên bản product, vd. 'Claude Opus 5.5', 'Seedance 2.0'."
    )


class IdentityV02(BaseModel):
    name: TextFact
    website: str | None = Field(default=None, description="Code điền từ URL gốc. LLM để null.")
    tagline: TextFact | None = None
    description: TextFact | None = None
    category: TextFact | None = Field(
        default=None, description="Loại product, vd. 'AI assistant', 'AI video generator'."
    )
    company: TextFact | None = None
    version: TextFact | None = Field(
        default=None, description="Phiên bản product nếu trang ghi rõ."
    )
    models: list[ModelVersion] = Field(
        default_factory=list, description="Các model AI product đang cung cấp."
    )


class Plan(Fact):
    """1 dòng = 1 plan × 1 chu kỳ trả. Giá số là con số in trên trang, không tự tính."""

    name: str = Field(description="Tên plan đúng như trên trang, vd. 'Pro'.")
    currency: str | None = Field(
        default=None, description="Tiền tệ in trên trang, mã ISO 4217, vd. USD, VND."
    )
    list_price: float | None = Field(
        default=None,
        description="Giá niêm yết in trên trang; 0 nếu Free; null nếu 'Contact sales'.",
    )
    promo_price: float | None = Field(
        default=None, description="Giá khuyến mãi in trên trang; null nếu không có."
    )
    promo_terms: str | None = Field(
        default=None, description="Điều kiện của giá khuyến mãi, vd. 'tháng đầu'."
    )
    price_unit: PriceUnit | None = Field(
        default=None, description="Giá tính cho đơn vị nào. Bắt buộc khi có list_price."
    )
    billing_cycle: BillingCycle | None = Field(
        default=None, description="Cách trả tiền. Bắt buộc khi có list_price."
    )
    price_text: str = Field(description="Giá nguyên văn, vd. '$17/month billed annually'.")
    limits: list[str] = Field(
        default_factory=list, description="Giới hạn của plan, nguyên văn từ trang."
    )
    audience: str | None = Field(default=None, description="Đối tượng, vd. 'individuals'.")

    @model_validator(mode="after")
    def unit_and_cycle_required_with_price(self) -> Plan:
        if self.list_price is not None and (self.price_unit is None or self.billing_cycle is None):
            raise ValueError("plan có list_price thì price_unit và billing_cycle là bắt buộc")
        return self


class UsagePrice(Fact):
    """Giá theo đơn vị dùng (token, giây video, credit). Không phải plan đăng ký."""

    name: str = Field(description="vd. 'API input'.")
    unit: str = Field(description="vd. '1M tokens', 'second of video'.")
    price: float
    currency: str | None = Field(default=None, description="Mã ISO 4217.")


class Pricing(BaseModel):
    currency: TextFact | None = Field(
        default=None, description="Tiền tệ chính trên trang giá (ISO 4217)."
    )
    region: str | None = Field(default=None, description="Vùng IP lúc crawl. Code điền.")
    locale: str | None = Field(default=None, description="Locale lúc crawl. Code điền.")
    default_view: str | None = Field(
        default=None, description="Tab / chu kỳ trang giá hiển thị mặc định, vd. 'monthly'."
    )
    other_views: list[str] = Field(
        default_factory=list,
        description="Các tab khác có trên trang giá mà nội dung chưa lấy được.",
    )
    plans: list[Plan] = Field(default_factory=list)
    usage_prices: list[UsagePrice] = Field(default_factory=list)
    free_plan: BoolFact | None = None
    trial_days: IntFact | None = None


class Feature(Fact):
    id: str | None = Field(default=None, description="Code điền (f1, f2…). LLM để null.")
    name: str
    description: str | None = None
    screenshot_ids: list[str] = Field(
        default_factory=list, description="Code điền ở 1.3. LLM để rỗng."
    )


class UseCase(Fact):
    title: str


class Limitation(Fact):
    text: str


class Conflict(BaseModel):
    field: str = Field(description="Đường dẫn trường, vd. 'pricing.plans[0].list_price'.")
    values: list[float | str]
    source_ids: list[str]


# ---------------------------------------------------------------- v0.3
class OwnerEdited(BaseModel):
    """`origin: owner` thì bắt buộc `edited_by` (UUID) + `edited_at` (UTC); origin khác thì cấm."""

    edited_by: str | None = Field(default=None, pattern=UUID_PATTERN)
    edited_at: str | None = Field(default=None, pattern=UTC_PATTERN)

    @model_validator(mode="after")
    def owner_edit_fields(self) -> OwnerEdited:
        origin = getattr(self, "origin", None)
        has = self.edited_by is not None or self.edited_at is not None
        if origin == "owner" and (self.edited_by is None or self.edited_at is None):
            raise ValueError("origin owner thì edited_by và edited_at là bắt buộc")
        if origin != "owner" and has:
            raise ValueError("edited_by / edited_at chỉ dùng cho origin owner")
        return self


class SourcedItem(OwnerEdited):
    """Mục có nguồn: `crawled` bắt buộc `source_id` + `evidence`; `owner` có thể không có nguồn."""

    origin: ItemOrigin
    source_id: str | None = Field(default=None, pattern=SOURCE_ID_PATTERN)
    evidence: str | None = Field(default=None, min_length=1, max_length=EVIDENCE_MAX)
    extracted_via: ExtractedVia | None = None

    @model_validator(mode="after")
    def crawled_needs_source(self) -> SourcedItem:
        if self.origin == "crawled" and (self.source_id is None or self.evidence is None):
            raise ValueError("origin crawled thì source_id và evidence là bắt buộc")
        return self


class Offer(SourcedItem):
    price_text: str | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    original_amount: float | None = Field(default=None, ge=0)
    availability: Availability = "unknown"
    seller: str | None = None
    platform: str | None = None
    variant_ref: str | None = Field(default=None, pattern=VARIANT_ID_PATTERN)

    @model_validator(mode="after")
    def currency_required_with_amount(self) -> Offer:
        if (self.amount is not None or self.original_amount is not None) and self.currency is None:
            raise ValueError("offer có amount thì currency là bắt buộc")
        return self


class VariantAttribute(BaseModel):
    key: str
    value: str


class Variant(SourcedItem):
    id: str = Field(pattern=VARIANT_ID_PATTERN)
    name: str
    attributes: list[VariantAttribute] = Field(default_factory=list)
    sku: str | None = None
    selected: bool = False


class Spec(SourcedItem):
    key: str
    value: str
    unit: str | None = None


class Image(SourcedItem):
    url: str | None = None
    storage_path: str | None = None
    alt: str | None = None
    role: ImageRole
    variant_ref: str | None = Field(default=None, pattern=VARIANT_ID_PATTERN)
    generic: bool = False

    @model_validator(mode="after")
    def has_location(self) -> Image:
        if self.url is None and self.storage_path is None:
            raise ValueError("ảnh cần url hoặc storage_path")
        return self


class Media(BaseModel):
    images: list[Image] = Field(default_factory=list)


class PreviousValue(BaseModel):
    """Giá trị đã crawl bị owner ghi đè."""

    value: str
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    evidence: str = Field(min_length=1, max_length=EVIDENCE_MAX)


class IdentityFact(SourcedItem):
    """Fact văn bản của `identity` mà owner được sửa. `TextFact` v0.2 đọc được như `crawled`."""

    value: str
    previous: PreviousValue | None = None

    @model_validator(mode="after")
    def previous_only_for_owner(self) -> IdentityFact:
        if self.previous is not None and self.origin != "owner":
            raise ValueError("previous chỉ dùng khi origin owner")
        return self


class Identity(IdentityV02):
    name: IdentityFact  # type: ignore[assignment]
    description: IdentityFact | None = None  # type: ignore[assignment]
    category: IdentityFact | None = None  # type: ignore[assignment]
    product_kind: ProductKind | None = None
    brand_name: IdentityFact | None = None
    sku: IdentityFact | None = None
    gtin: IdentityFact | None = None


class Claim(OwnerEdited):
    origin: Origin
    source_id: str | None = Field(default=None, pattern=SOURCE_ID_PATTERN)
    evidence: str | None = Field(default=None, max_length=EVIDENCE_MAX)


class Audience(Claim):
    segment: str
    jtbd: str | None = None


class Usp(Claim):
    text: str


class Competitor(Claim):
    name: str
    url: str | None = None


class Brand(Claim):
    logo_asset_id: str | None = None
    colors: list[str] = Field(default_factory=list)
    tone: str | None = None


class Compliance(Claim):
    forbidden_claims: list[str] = Field(default_factory=list)
    approved_claims: list[str] = Field(default_factory=list)


class Affiliate(Claim):
    """DEPRECATED. Chỉ để đọc dữ liệu v0.2."""

    link: str | None = None
    commission: str | None = None


class Quality(BaseModel):
    completeness: float | None = Field(default=None, ge=0, le=1)
    conflicts: list[Conflict] = Field(default_factory=list)


class PKBData(BaseModel):
    """Nội dung cột `product_knowledge.data`."""

    schema_version: SchemaVersion
    identity: Identity
    pricing: Pricing | None = None
    features: list[Feature] = Field(default_factory=list)
    use_cases: list[UseCase] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    specs: list[Spec] = Field(default_factory=list)
    media: Media | None = None
    audiences: list[Audience] = Field(default_factory=list)
    usp: list[Usp] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list)
    brand: Brand | None = None
    compliance: Compliance | None = None
    affiliate: Affiliate | None = None
    quality: Quality | None = None

    @model_validator(mode="after")
    def kind_rules(self) -> PKBData:
        kind = self.identity.product_kind
        v03 = self.schema_version == "0.3"
        if v03 and kind is None:
            raise ValueError("schema_version 0.3 thì identity.product_kind là bắt buộc")
        if kind == "physical":
            if not self.offers:
                raise ValueError("physical thì offers cần ít nhất 1 phần tử")
        else:  # software, hoặc v0.2 không có product_kind
            if self.pricing is None:
                raise ValueError("software thì pricing là bắt buộc")
            if self.offers or self.variants or self.specs:
                raise ValueError("offers, variants, specs chỉ dùng cho physical")
        if v03:
            if self.affiliate is not None:
                raise ValueError("affiliate đã deprecated, dữ liệu 0.3 không được có")
            claims = [*self.audiences, *self.usp, *self.competitors, self.brand, self.compliance]
            if any(c is not None and c.origin == "merchant" for c in claims):
                raise ValueError("origin 'merchant' đã đổi thành 'owner' trong 0.3")
        return self

    @model_validator(mode="after")
    def refs_are_consistent(self) -> PKBData:
        ids = [v.id for v in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("variants[].id phải duy nhất")
        if sum(v.selected for v in self.variants) > 1:
            raise ValueError("chỉ được 1 variant selected")
        images = self.media.images if self.media else []
        if sum(i.role == "hero" for i in images) > 1:
            raise ValueError("chỉ được 1 ảnh hero")
        refs = [o.variant_ref for o in self.offers] + [i.variant_ref for i in images]
        dangling = {r for r in refs if r is not None and r not in ids}
        if dangling:
            raise ValueError(f"variant_ref không trỏ tới variant nào: {sorted(dangling)}")
        return self


class Source(BaseModel):
    """1 phần tử của cột `product_knowledge.sources`."""

    id: str = Field(pattern=SOURCE_ID_PATTERN)
    url: str
    page_type: str
    fetched_at: str
    content_hash: str
    region: str | None = None
    locale: str | None = None
    variant: Literal["raw", "fit"] = Field(description="Bản markdown đã gửi cho LLM.")
    markdown_path: str | None = None
    image_paths: list[str] = Field(default_factory=list)
    structured_path: str | None = None
