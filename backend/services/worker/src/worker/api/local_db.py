"""Database JSON cục bộ cho pilot P1.

Adapter này giữ cùng ``Database`` protocol và các bất biến quan trọng của migration P1. Nó chỉ
phục vụ chạy thử trên một máy (``LOCAL_P1_MODE=1``), không thay Supabase và không dành cho nhiều
process ghi đồng thời.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from worker.api.db import Row
from worker.api.errors import DatabaseError


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _eq(value: Any, expression: str) -> bool:
    return not expression.startswith("eq.") or str(value) == expression[3:]


class LocalDatabase:
    """Persistence đơn tiến trình, có ghi file nguyên tử và RPC tương đương pilot."""

    def __init__(self, directory: str, owner_id: str) -> None:
        self.root = Path(directory).resolve()
        self.file = self.root / "db.json"
        self.owner_id = owner_id
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.file.exists():
            self._write(
                {
                    "merchants": [
                        {
                            "id": owner_id,
                            "user_id": owner_id,
                            "company_name": "Local P1 Demo",
                            "status": "active",
                        }
                    ],
                    "products": [],
                    "product_knowledge": [],
                    "script_revisions": [],
                    "generation_jobs": [],
                }
            )

    def _read(self) -> dict[str, list[Row]]:
        try:
            value = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DatabaseError(500, "local_db", "database local bị hỏng") from exc
        if not isinstance(value, dict):
            raise DatabaseError(500, "local_db", "database local không hợp lệ")
        return value

    def _write(self, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix(".json.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.file)

    @staticmethod
    def _table(data: dict[str, list[Row]], name: str) -> list[Row]:
        if name not in data:
            raise DatabaseError(404, "42P01", f"bảng local không tồn tại: {name}")
        return data[name]

    @staticmethod
    def _filter(rows: list[Row], filters: Mapping[str, str]) -> list[Row]:
        reserved = {"select", "order", "limit"}
        result = [
            row
            for row in rows
            if all(
                _eq(row.get(key), value) for key, value in filters.items() if key not in reserved
            )
        ]
        order = filters.get("order")
        if order:
            key, _, direction = order.partition(".")
            result.sort(key=lambda row: str(row.get(key, "")), reverse=direction == "desc")
        limit = filters.get("limit")
        if limit and limit.isdigit():
            result = result[: int(limit)]
        columns = filters.get("select")
        if columns and columns != "*":
            wanted = {column.strip() for column in columns.split(",")}
            result = [{key: value for key, value in row.items() if key in wanted} for row in result]
        return deepcopy(result)

    def get_user_id(self, jwt: str) -> str | None:
        return self.owner_id if jwt == "local-demo" else None

    def select(self, table: str, filters: Mapping[str, str], jwt: str | None = None) -> list[Row]:
        del jwt
        with self._lock:
            data = self._read()
            return self._filter(self._table(data, table), filters)

    def insert(self, table: str, row: Mapping[str, Any]) -> Row:
        with self._lock:
            data = self._read()
            target = self._table(data, table)
            value = deepcopy(dict(row))
            value.setdefault("id", str(uuid4()))
            if table == "products":
                if any(item.get("website_url") == value.get("website_url") for item in target):
                    raise DatabaseError(409, "23505", "website_url đã tồn tại")
                value.setdefault("name", None)
                value.setdefault("status", "draft")
                value.setdefault("current_knowledge_version", None)
            value.setdefault("created_at", _now())
            value.setdefault("updated_at", value["created_at"])
            target.append(value)
            self._write(data)
            return deepcopy(value)

    def delete_product(self, product_id: str) -> list[str]:
        """Xóa dữ liệu của một Product local sau khi mọi job đã dừng."""
        with self._lock:
            data = self._read()
            self._product(data, product_id)
            jobs = [row for row in data["generation_jobs"] if row.get("product_id") == product_id]
            if any(row.get("status") not in {"completed", "failed", "cancelled"} for row in jobs):
                raise DatabaseError(409, "23001", "dự án còn job đang chạy; hãy đợi job hoàn tất")
            job_ids = [str(row["id"]) for row in jobs]
            for table in ("generation_jobs", "script_revisions", "product_knowledge", "products"):
                data[table] = [row for row in data[table] if row.get("product_id", row.get("id")) != product_id]
            self._write(data)
            return job_ids

    def update(self, table: str, filters: Mapping[str, str], patch: Mapping[str, Any]) -> list[Row]:
        with self._lock:
            data = self._read()
            target = self._table(data, table)
            changed: list[Row] = []
            for row in target:
                if all(_eq(row.get(key), value) for key, value in filters.items()):
                    if row.get("status") in {"completed", "failed", "approved", "rejected"}:
                        raise DatabaseError(409, "23001", "bản ghi cuối không thể sửa")
                    row.update(deepcopy(dict(patch)))
                    row["updated_at"] = _now()
                    if row.get("status") in {"completed", "failed"}:
                        row["finished_at"] = _now()
                    changed.append(deepcopy(row))
            self._write(data)
            return changed

    def rpc(self, name: str, args: Mapping[str, Any]) -> Any:
        with self._lock:
            data = self._read()
            result = self._rpc(data, name, args)
            self._write(data)
            return deepcopy(result)

    def _product(self, data: dict[str, list[Row]], product_id: str) -> Row:
        product = next((row for row in data["products"] if row["id"] == product_id), None)
        if product is None:
            raise DatabaseError(404, "23503", "product không tồn tại")
        return product

    def _review(self, row: Row, decision: str, note: str | None, actor: str) -> dict[str, str]:
        transitions = {
            ("draft", "submit"): "in_review",
            ("draft", "reject"): "rejected",
            ("in_review", "approve"): "approved",
            ("in_review", "reject"): "rejected",
        }
        status = transitions.get((str(row.get("status")), decision))
        if status is None:
            raise DatabaseError(409, "23001", "chuyển trạng thái duyệt không hợp lệ")
        if status == "rejected" and not (note or "").strip():
            raise DatabaseError(422, "23514", "từ chối cần lý do")
        row.update(
            {
                "status": status,
                "review_note": note,
                "reviewed_by": actor,
                "reviewed_at": _now(),
                "updated_at": _now(),
            }
        )
        return {"status": status}

    def _rpc(self, data: dict[str, list[Row]], name: str, args: Mapping[str, Any]) -> Any:
        product_id = str(args.get("p_product_id", ""))
        if name == "create_pkb_version":
            self._product(data, product_id)
            versions = [
                int(row["version"])
                for row in data["product_knowledge"]
                if row["product_id"] == product_id
            ]
            version = max(versions, default=0) + 1
            data["product_knowledge"].append(
                {
                    "product_id": product_id,
                    "version": version,
                    "status": "draft",
                    "data": deepcopy(args["p_data"]),
                    "sources": deepcopy(args["p_sources"]),
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
            return version
        if name == "review_pkb":
            row = next(
                (
                    item
                    for item in data["product_knowledge"]
                    if item["product_id"] == product_id
                    and int(item["version"]) == int(args["p_version"])
                ),
                None,
            )
            if row is None:
                raise DatabaseError(404, "P0002", "PKB không tồn tại")
            result = self._review(
                row, str(args["p_decision"]), args.get("p_note"), str(args["p_actor"])
            )
            if result["status"] == "approved":
                self._product(data, product_id)["current_knowledge_version"] = row["version"]
            return result
        if name == "create_script_revision":
            pkb_version = int(args["p_knowledge_version"])
            approved = any(
                row["product_id"] == product_id
                and int(row["version"]) == pkb_version
                and row["status"] == "approved"
                for row in data["product_knowledge"]
            )
            if not approved:
                raise DatabaseError(422, "23514", "script cần PKB đã duyệt")
            key = str(args["p_idempotency_key"])
            old = next(
                (
                    row
                    for row in data["script_revisions"]
                    if row["product_id"] == product_id and row["idempotency_key"] == key
                ),
                None,
            )
            if old:
                return old["revision"]
            revisions = [
                int(row["revision"])
                for row in data["script_revisions"]
                if row["product_id"] == product_id
            ]
            revision = max(revisions, default=0) + 1
            data["script_revisions"].append(
                {
                    "product_id": product_id,
                    "revision": revision,
                    "knowledge_version": pkb_version,
                    "status": "draft",
                    "content": deepcopy(args["p_content"]),
                    "parent_revision": args.get("p_parent_revision"),
                    "report": deepcopy(args.get("p_report")),
                    "cost_breakdown": deepcopy(args.get("p_cost_breakdown")),
                    "idempotency_key": key,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
            return revision
        if name == "review_script_revision":
            row = next(
                (
                    item
                    for item in data["script_revisions"]
                    if item["product_id"] == product_id
                    and int(item["revision"]) == int(args["p_revision"])
                ),
                None,
            )
            if row is None:
                raise DatabaseError(404, "P0002", "script không tồn tại")
            return self._review(
                row, str(args["p_decision"]), args.get("p_note"), str(args["p_actor"])
            )
        if name == "create_generation_job":
            key = str(args["p_idempotency_key"])
            old = next(
                (
                    row
                    for row in data["generation_jobs"]
                    if row["product_id"] == product_id and row["idempotency_key"] == key
                ),
                None,
            )
            if old:
                return old["id"]
            job_type = str(args["p_job_type"])
            script_revision = args.get("p_script_revision")
            pkb_version = args.get("p_pkb_version")
            if job_type == "video":
                script = next(
                    (
                        row
                        for row in data["script_revisions"]
                        if row["product_id"] == product_id
                        and int(row["revision"]) == int(script_revision or 0)
                    ),
                    None,
                )
                wrong_knowledge = script and int(script["knowledge_version"]) != int(
                    pkb_version or 0
                )
                if not script or script["status"] != "approved" or wrong_knowledge:
                    raise DatabaseError(422, "23514", "video cần đúng script đã duyệt")
            job_id = str(uuid4())
            data["generation_jobs"].append(
                {
                    "id": job_id,
                    "product_id": product_id,
                    "job_type": job_type,
                    "status": "queued",
                    "error": None,
                    "attempts": 0,
                    "pkb_version": pkb_version,
                    "script_revision": script_revision,
                    "render_profile": deepcopy(args.get("p_render_profile")),
                    "n8n_execution_id": args.get("p_n8n_execution_id"),
                    "input_snapshot": deepcopy(args.get("p_input_snapshot")),
                    "result_manifest": None,
                    "cost_breakdown": None,
                    "idempotency_key": key,
                    "created_at": _now(),
                    "updated_at": _now(),
                    "finished_at": None,
                }
            )
            return job_id
        raise DatabaseError(404, "42883", f"RPC local chưa hỗ trợ: {name}")
