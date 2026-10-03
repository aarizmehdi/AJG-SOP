"""Strict production batch preview/apply using the same permanent purge service as the API.

Preview writes only a local inventory file. Apply requires that exact inventory,
exactly two matching AJG test policies, and a verified existing System Admin.
"""

import argparse
import asyncio
import json
from pathlib import Path

from firebase_admin import auth

from apps.api.app.auth.identity import FirebaseIdentityProvider
from apps.api.app.config import Settings
from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.repositories.foundation_persistence import MongoFoundationPersistence
from apps.api.app.repositories.purge_repository import PurgeRepository
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_purge_service import PolicyPurgeService
from apps.api.app.services.storage_service import S3ArtifactStore
from packages.contracts.purge import PurgeConfirmation, PurgeGraph, PurgePreview
from services.ingestion.indexing.pinecone_index import PineconeRetrievalIndex

EXPECTED = {
    "policy-424b545081b8": ("Store, Excise & Gate SOP — Part 1", "SOPs_Store_Excise_Gate_1 (1).md"),
    "policy-f0b8e23ee8de": ("Procedure for Store returns", "SOP-76_Store_Returns_LIVE.md"),
}


async def run(args: argparse.Namespace) -> None:
    settings = Settings(_env_file=None)
    if settings.app_mode != "live":
        raise ValueError("This maintenance tool requires explicit live configuration")
    persistence = MongoFoundationPersistence(settings.mongodb_uri, settings.mongodb_database)
    try:
        store = FoundationStore()
        await persistence.load(store)
        database = persistence._database
        profiles = await database.employee_profiles.find(
            {"organization_id": "ajt", "active": True, "application_roles": "system_admin"}
        ).to_list(None)
        if len(profiles) != 1:
            raise ValueError(
                "Expected one existing active AJG System Admin; do not guess the actor"
            )
        profiles[0].pop("_id", None)
        profile = EmployeeProfile.model_validate(profiles[0])
        identity = FirebaseIdentityProvider(settings)
        user = auth.get_user(
            profile.identity_subject.removeprefix("firebase|"), app=identity.firebase_app
        )
        if user.disabled:
            raise ValueError("Existing System Admin Firebase identity is disabled")
        repository = PurgeRepository(store, database)
        assert (
            settings.s3_access_key_id
            and settings.s3_secret_access_key
            and settings.pinecone_api_key
        )
        artifacts = S3ArtifactStore(
            settings.s3_bucket,
            settings.s3_region,
            settings.s3_endpoint_url,
            settings.s3_access_key_id.get_secret_value(),
            settings.s3_secret_access_key.get_secret_value(),
        )
        index = PineconeRetrievalIndex(
            settings.pinecone_api_key.get_secret_value(),
            settings.pinecone_index,
            settings.pinecone_namespace_prefix,
        )
        service = PolicyPurgeService(repository, artifacts, index)
        policies = [p for p in store.policies.values() if p.organization_id == "ajt"]

        def check_batch() -> None:
            if {p.id for p in policies} != set(EXPECTED) or len(policies) != 2:
                raise ValueError(
                    f"STOP: production inventory differs: {[(p.id, p.title) for p in policies]}"
                )
            for p in policies:
                title, file_name = EXPECTED[p.id]
                sources = [
                    s
                    for s in store.sources.values()
                    if s.organization_id == "ajt" and s.policy_id == p.id
                ]
                if p.title != title or len(sources) != 1 or sources[0].file_name != file_name:
                    raise ValueError(
                        f"STOP: policy/source identity is ambiguous: {p.id}, {p.title}"
                    )

        if not args.apply and not args.verify:
            check_batch()
            inventory = []
            for policy in sorted(policies, key=lambda p: p.id):
                preview = await service.preview(profile, policy.id)
                graph = await repository.graph("ajt", policy.id)
                inventory.append({"preview": preview.model_dump(), "graph": graph.model_dump()})
                print(json.dumps(preview.model_dump(), ensure_ascii=False))
            args.inventory.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        if {i["preview"]["policy_id"] for i in inventory} != set(EXPECTED):
            raise ValueError("Inventory must identify exactly the two approved test policies")
        if args.verify:
            for item in inventory:
                graph = PurgeGraph.model_validate(item["graph"])
                print(
                    json.dumps(
                        {"policy_id": graph.policy_id, "remaining": await service.verify(graph)}
                    )
                )
            return
        async with repository.write_guard():
            # Freeze supported application writers for the entire batch; validate BOTH previews
            # before the first destructive operation. Existing completed retries are permitted.
            rows = await repository.rows("ajt")
            live = {p["id"] for p in rows.get("policies", [])}
            if live - set(EXPECTED):
                raise ValueError("STOP: additional policy appeared since preview")
            for item in inventory:
                old = PurgePreview.model_validate(item["preview"])
                operation = await repository.operation("ajt", old.policy_id)
                if not operation:
                    policy = next(
                        (p for p in rows.get("policies", []) if p["id"] == old.policy_id), None
                    )
                    sources = [
                        s
                        for s in rows.get("source_documents", [])
                        if s.get("policy_id") == old.policy_id
                    ]
                    title, filename = EXPECTED[old.policy_id]
                    if (
                        policy is None
                        or policy["title"] != title
                        or len(sources) != 1
                        or sources[0].get("file_name") != filename
                    ):
                        raise ValueError("STOP: policy/source identity changed before apply")
                    current = await service.preview(profile, old.policy_id)
                    if current != old:
                        raise ValueError(
                            "STOP: production preview changed; run read-only preview again"
                        )
            for item in inventory:
                preview = PurgePreview.model_validate(item["preview"])
                result = await service.purge(
                    profile,
                    preview.policy_id,
                    PurgeConfirmation(
                        title=preview.title,
                        phrase="DELETE PERMANENTLY",
                        preview_token=preview.preview_token,
                    ),
                )
                print(
                    json.dumps({"title": preview.title, **result.model_dump()}, ensure_ascii=False)
                )
                if result.status not in {"complete", "already_complete"}:
                    raise RuntimeError(
                        "Purge stage failed. Do not proceed to the next policy; retry safely."
                    )
    finally:
        await persistence.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    asyncio.run(run(parser.parse_args()))
