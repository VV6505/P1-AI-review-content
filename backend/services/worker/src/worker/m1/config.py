"""Cấu hình crawl M1 (một chỗ duy nhất). Mặc định bằng spike `spikes/m1-crawl-extract/crawl.py`.

Đè giá trị bằng biến môi trường `M1_CRAWL_<TÊN_HOA>`, ví dụ `M1_CRAWL_MAX_PAGES=20`.
Trường kiểu dict (`type_quota`) truyền dạng JSON. Trường tuple (`languages`, `extra_host_types`)
nhận danh sách cách nhau bằng dấu phẩy (`en,vi`) hoặc JSON.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

ENV_PREFIX = "M1_CRAWL_"


class CrawlSettings(BaseModel):
    # User-Agent định danh dự án (NFR-05). Không giả trình duyệt, không đổi UA ngẫu nhiên.
    # Product token (phần trước dấu /) phải khớp nhóm User-agent trong robots.txt.
    # Đổi qua M1_CRAWL_USER_AGENT khi cần.
    user_agent: str = "AIReviewContentFactory/0.1"
    max_pages: int = 30  # ≤ 30 trang/product, tính cả trang chủ và host phụ
    # Trang từ host phụ (vd. support.claude.com), tính chung trong max_pages
    max_extra_host_pages: int = 5
    # Host phụ chỉ bù FAQ / giá (help center), không lấy docs để khỏi chiếm slot của host gốc.
    extra_host_types: tuple[str, ...] = ("faq", "pricing")
    min_interval_s: float = 1.0  # ≤ 1 request/giây/host (mở trang, tải robots hay sitemap đều tính)
    max_child_sitemaps: int = 5  # sitemap index có thể rất lớn
    max_sitemap_urls: int = 5000
    http_timeout_s: float = 20.0
    page_timeout_ms: int = 45_000
    render_delay_s: float = 3.0  # chờ thêm sau domcontentloaded cho trang SPA
    min_home_chars: int = 200  # trang chủ ít chữ hơn mức này → coi là không có nội dung
    # Hạn mức trang theo page_type để 1 loại (thường là features) không chiếm hết slot.
    # Hết ứng viên trong hạn mức thì lấp tiếp theo điểm.
    type_quota: dict[str, int] = {
        "other": 1,
        "pricing": 4,
        "features": 10,
        "docs": 6,
        "faq": 4,
        "compare": 3,
        "changelog": 2,
    }
    # Ngôn ngữ trang được crawl, theo thứ tự ưu tiên. Cùng 1 trang có nhiều bản dịch thì chỉ giữ
    # bản ngôn ngữ đứng trước. Env: M1_CRAWL_LANGUAGES=en,vi
    languages: tuple[str, ...] = ("en", "vi")
    # Vùng IP và locale lúc crawl (quy tắc giá số 6). Đặt tay như spike, chưa đo.
    region: str = "VN"
    locale: str = "en-US"

    @property
    def ua_token(self) -> str:
        """Product token của UA, dùng để khớp nhóm `User-agent` trong robots.txt."""
        return self.user_agent.split("/", 1)[0].lower()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> CrawlSettings:
        env = os.environ if env is None else env
        values: dict[str, Any] = {}
        for name, field in cls.model_fields.items():
            raw = env.get(ENV_PREFIX + name.upper())
            if raw is None:
                continue
            if field.annotation in (str, int, float):
                values[name] = raw
            elif field.annotation == tuple[str, ...] and not raw.lstrip().startswith("["):
                values[name] = [v.strip().lower() for v in raw.split(",") if v.strip()]
            else:
                values[name] = json.loads(raw)
        return cls(**values)


class CrawlOptions(BaseModel):
    """Tuỳ chọn theo từng product (FR-02): host phụ chỉ crawl khi được bật, không tự bật."""

    # Nhận cả *.<domain gốc> (vd. support.claude.com cho claude.com). Không bật cho Dreamina,
    # vì domain gốc của dreamina.capcut.com là capcut.com, một sản phẩm khác.
    allow_subdomains: bool = False
    extra_hosts: list[str] = []
