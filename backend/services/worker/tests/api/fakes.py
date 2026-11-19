"""Database giả cho test API: ghi lại lời gọi, trả kết quả đã lập trình. Không cần mạng."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from worker.api.db import Row
from worker.api.errors import DatabaseError

OWNER_ID = "00000000-0000-4000-8000-0000000000a1"
OWNER_JWT = "owner-jwt"
PRODUCT_ID = "00000000-0000-4000-8000-0000000000c1"
JOB_ID = "00000000-0000-4000-8000-0000000000d1"


class FakeDb:
    def __init__(self) -> None:
        self.users: dict[str, str] = {OWNER_JWT: OWNER_ID}
        self.tables: dict[str, list[Row]] = {}
        self.rpc_results: dict[str, Any] = {}
        self.errors: dict[str, DatabaseError] = {}  # khoá: tên RPC hoặc "table:<tên>"
        self.calls: list[tuple[str, Any]] = []

    def _maybe_raise(self, key: str) -> None:
        if key in self.errors:
            raise self.errors[key]

    def rpc(self, name: str, args: Mapping[str, Any]) -> Any:
        self.calls.append(("rpc:" + name, dict(args)))
        self._maybe_raise(name)
        return self.rpc_results.get(name)

    def select(self, table: str, filters: Mapping[str, str], jwt: str | None = None) -> list[Row]:
        self.calls.append(("select:" + table, {"filters": dict(filters), "jwt": jwt}))
        self._maybe_raise("table:" + table)
        return list(self.tables.get(table, []))

    def insert(self, table: str, row: Mapping[str, Any]) -> Row:
        self.calls.append(("insert:" + table, dict(row)))
        self._maybe_raise("table:" + table)
        return {"id": PRODUCT_ID, "status": "draft", "name": row.get("name"), **row}

    def update(self, table: str, filters: Mapping[str, str], patch: Mapping[str, Any]) -> list[Row]:
        self.calls.append(("update:" + table, {"filters": dict(filters), "patch": dict(patch)}))
        self._maybe_raise("table:" + table)
        return list(self.tables.get(table, []))

    def get_user_id(self, jwt: str) -> str | None:
        return self.users.get(jwt)

    def last(self, kind: str) -> Any:
        return [a for k, a in self.calls if k == kind][-1]
