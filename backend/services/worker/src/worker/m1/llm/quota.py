"""Phân biệt 429 RPM với 429 RPD và tính giờ reset quota ngày (ADR-0002, #70).

Gemini trả 429 `RESOURCE_EXHAUSTED`. Trong `error.details` có mục `google.rpc.QuotaFailure`,
mỗi `violations[]` ghi `quotaId` / `quotaMetric`, vd.
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` (hết RPD) hoặc
`GenerateRequestsPerMinutePerProjectPerModel-FreeTier` (vượt RPM). Cách nhận diện:
1. Có violation chứa `PerDay` → RPD.
2. Không thì có violation chứa `PerMinute` → RPM.
3. Không có QuotaFailure: message chứa "per day" / "daily" → RPD, còn lại → RPM.
Chưa có response 429 thật (#70: 0 lần 429). Fixture test là dữ liệu synthetic,
theo dạng lỗi trong tài liệu Google.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

# RPD reset lúc 0h giờ Thái Bình Dương (có giờ mùa hè). Windows cần gói tzdata.
PACIFIC = ZoneInfo("America/Los_Angeles")
QUOTA_FAILURE = "type.googleapis.com/google.rpc.QuotaFailure"
RETRY_INFO = "type.googleapis.com/google.rpc.RetryInfo"
_DAILY_TEXT = re.compile(r"per[ _-]?day|daily", re.IGNORECASE)


def _error_details(details: Any) -> list[dict[str, Any]]:
    """Lấy `error.details[]` từ JSON lỗi (dạng `{"error": {...}}` hoặc đã là `{...}`)."""
    if not isinstance(details, dict):
        return []
    err = details.get("error", details)
    items = err.get("details") if isinstance(err, dict) else None
    return [d for d in items or [] if isinstance(d, dict)]


def classify_429(details: Any, message: str = "") -> Literal["rpm", "rpd"]:
    ids: list[str] = []
    for d in _error_details(details):
        if d.get("@type") == QUOTA_FAILURE:
            for v in d.get("violations") or []:
                if isinstance(v, dict):
                    ids.append(f"{v.get('quotaId', '')} {v.get('quotaMetric', '')}")
    if any("PerDay" in i for i in ids):
        return "rpd"
    if any("PerMinute" in i for i in ids):
        return "rpm"
    if not message and isinstance(details, dict):
        err = details.get("error", details)
        message = str(err.get("message", "")) if isinstance(err, dict) else ""
    return "rpd" if _DAILY_TEXT.search(message) else "rpm"


def retry_delay_s(details: Any) -> float | None:
    """`RetryInfo.retryDelay` (vd. "39s") nếu provider gợi ý thời gian chờ."""
    for d in _error_details(details):
        if d.get("@type") == RETRY_INFO:
            m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                return float(m.group(1))
    return None


def next_daily_reset(now: datetime) -> datetime:
    """0h giờ Thái Bình Dương kế tiếp, trả về UTC. `now` phải có múi giờ."""
    local = now.astimezone(PACIFIC)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=PACIFIC)
    return midnight.astimezone(UTC)
