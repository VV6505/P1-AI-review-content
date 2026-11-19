from pathlib import Path

import pytest

from worker.api.errors import DatabaseError
from worker.api.local_db import LocalDatabase


def test_local_p1_keeps_two_approval_gates(tmp_path: Path) -> None:
    owner = "00000000-0000-4000-8000-000000000001"
    db = LocalDatabase(str(tmp_path), owner)
    product = db.insert(
        "products",
        {
            "merchant_id": owner,
            "website_url": "https://example.com",
            "name": "Example",
            "status": "draft",
            "current_knowledge_version": None,
        },
    )
    version = db.rpc(
        "create_pkb_version",
        {
            "p_product_id": product["id"],
            "p_data": {"schema_version": "0.3"},
            "p_sources": [],
        },
    )
    with pytest.raises(DatabaseError):
        db.rpc(
            "create_script_revision",
            {
                "p_product_id": product["id"],
                "p_knowledge_version": version,
                "p_content": {},
                "p_idempotency_key": "script-1",
            },
        )
    db.rpc(
        "review_pkb",
        {
            "p_product_id": product["id"],
            "p_version": version,
            "p_actor": owner,
            "p_decision": "submit",
            "p_note": None,
        },
    )
    db.rpc(
        "review_pkb",
        {
            "p_product_id": product["id"],
            "p_version": version,
            "p_actor": owner,
            "p_decision": "approve",
            "p_note": None,
        },
    )
    revision = db.rpc(
        "create_script_revision",
        {
            "p_product_id": product["id"],
            "p_knowledge_version": version,
            "p_content": {"schema_version": "p1-ac-03.v1-draft"},
            "p_idempotency_key": "script-1",
            "p_parent_revision": None,
            "p_report": {},
            "p_cost_breakdown": {},
        },
    )
    with pytest.raises(DatabaseError):
        db.rpc(
            "create_generation_job",
            {
                "p_product_id": product["id"],
                "p_job_type": "video",
                "p_idempotency_key": "video-1",
                "p_input_snapshot": {},
                "p_pkb_version": version,
                "p_script_revision": revision,
                "p_n8n_execution_id": None,
                "p_render_profile": {},
            },
        )
    for decision in ("submit", "approve"):
        db.rpc(
            "review_script_revision",
            {
                "p_product_id": product["id"],
                "p_revision": revision,
                "p_actor": owner,
                "p_decision": decision,
                "p_note": None,
            },
        )
    job = db.rpc(
        "create_generation_job",
        {
            "p_product_id": product["id"],
            "p_job_type": "video",
            "p_idempotency_key": "video-1",
            "p_input_snapshot": {},
            "p_pkb_version": version,
            "p_script_revision": revision,
            "p_n8n_execution_id": "local",
            "p_render_profile": {"ratio": "16:9"},
        },
    )
    assert db.select("generation_jobs", {"id": f"eq.{job}"})[0]["status"] == "queued"
