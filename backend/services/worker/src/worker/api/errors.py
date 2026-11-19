"""Lỗi API. Trả về dạng `{"detail": "..."}` (quy ước của api-contract)."""

from __future__ import annotations

from typing import Any

# SQLSTATE do Postgres/RPC của `20261117020000_p1_pipeline_persistence.sql` trả về → HTTP status.
SQLSTATE_TO_STATUS: dict[str, int] = {
    "42501": 403,  # insufficient_privilege: actor không sở hữu product
    "23503": 404,  # foreign_key_violation: không có product / version
    "P0002": 404,  # no_data_found
    "23505": 409,  # unique_violation: chỉ mục chống chạy trùng, URL đã có
    "23001": 409,  # restrict_violation: chuyển trạng thái sai, bản đã khoá
    "23514": 422,  # check_violation: PKB chưa duyệt, thiếu lý do, dữ liệu sai dạng
    "22P02": 422,  # invalid_text_representation
}


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


class DatabaseError(Exception):
    """Lỗi từ PostgREST/Postgres. `code` là SQLSTATE (hoặc mã PostgREST), `message` là lời của
    DB."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def to_api_error(self) -> ApiError:
        mapped = SQLSTATE_TO_STATUS.get(self.code)
        if mapped is not None:
            return ApiError(mapped, self.message)
        if 400 <= self.status < 500:
            return ApiError(422, self.message)
        return ApiError(502, "database không phản hồi đúng")


def error_body(detail: Any) -> dict[str, Any]:
    return {"detail": detail}
