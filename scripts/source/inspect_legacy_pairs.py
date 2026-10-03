"""Inspect AJG source artifacts; repair verified legacy pairs only with --apply.

The default mode performs read-only MongoDB and S3 requests. Never infer file
identity from a filename or Mongo media type: the first object bytes decide it.
"""

import argparse
import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import boto3
import httpx
from pymongo import AsyncMongoClient

from packages.contracts.common import utc_now


@dataclass(frozen=True)
class Probe:
    uri: str
    exists: bool
    kind: str
    size: int | None
    content_type: str | None
    sha256: str | None = None
    heading_policy_numbers: tuple[str, ...] = ()


_explicit_number = re.compile(
    r"\b(?:SOP|Policy)\s*(?:No\.?|Number|#|-)?\s*(\d+(?:[.-]\d+)*)\b",
    re.IGNORECASE,
)


def heading_policy_numbers(content: str) -> tuple[str, ...]:
    numbers: set[str] = set()
    for line in content.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+", line) or re.match(
            r"^\s*(?:SOP|Policy)\b", line, re.IGNORECASE
        ):
            numbers.update(_explicit_number.findall(line))
    return tuple(sorted(numbers))


def object_key(uri: str, bucket: str, organization_id: str) -> str:
    prefix = f"s3://{bucket}/{organization_id}/"
    if not uri.startswith(prefix):
        raise ValueError("Artifact URI is outside the selected organization and bucket")
    return uri[len(f"s3://{bucket}/") :]


def legacy_markdown_uri(source: dict[str, Any], bucket: str, organization_id: str) -> str:
    name = source["file_name"]
    return f"s3://{bucket}/{organization_id}/sources/{source['id']}/original/{name}"


def probe_object(
    client: Any, bucket: str, organization_id: str, uri: str, *, hash_text: bool = False
) -> Probe:
    key = object_key(uri, bucket, organization_id)
    try:
        metadata = client.head_object(Bucket=bucket, Key=key)
    except client.exceptions.NoSuchKey:
        return Probe(uri, False, "missing", None, None)
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return Probe(uri, False, "missing", None, None)
        raise
    size = int(metadata["ContentLength"])
    response = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-31")
    try:
        signature = response["Body"].read(32)
    finally:
        response["Body"].close()
    kind = (
        "pdf" if signature.startswith(b"%PDF-") else "text" if b"\0" not in signature else "binary"
    )
    digest = None
    heading_numbers: tuple[str, ...] = ()
    if hash_text and kind == "text" and size <= 10 * 1024 * 1024:
        response = client.get_object(Bucket=bucket, Key=key)
        try:
            content = response["Body"].read()
            digest = hashlib.sha256(content).hexdigest()
            heading_numbers = heading_policy_numbers(content.decode("utf-8", errors="replace"))
        finally:
            response["Body"].close()
    return Probe(uri, True, kind, size, metadata.get("ContentType"), digest, heading_numbers)


def classify(
    source: dict[str, Any], original: Probe, structured: Probe | None, old: Probe | None
) -> str:
    if not original.exists or (structured is not None and not structured.exists):
        return "corrupted/missing artifact"
    if structured is not None:
        return (
            "correct new PDF + Markdown pair"
            if original.kind == "pdf" and structured.kind == "text"
            else "corrupted/missing artifact"
        )
    if original.kind == "text" and source.get("source_format") == "markdown":
        return "genuine Markdown-only source"
    if original.kind == "pdf" and source.get("source_format") == "markdown":
        return "legacy paired source with mismatched metadata"
    return "corrupted/missing artifact"


def preview_probe(s3: Any, bucket: str, key: str) -> dict[str, object]:
    """Exercise a short-lived GET signature without printing its bearer URL."""
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=120,
    )
    with httpx.stream("GET", url, headers={"Range": "bytes=0-31"}, timeout=20) as response:
        signature = next(response.iter_bytes(chunk_size=32), b"")
        return {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "content_disposition": response.headers.get("content-disposition"),
            "content_range": response.headers.get("content-range"),
            "signature_is_pdf": signature.startswith(b"%PDF-"),
            "received_bytes": len(signature),
        }


async def inspect(
    *,
    organization_id: str,
    source_id: str | None,
    apply: bool,
    actor_id: str,
    probe_presigned_preview: bool = False,
) -> None:
    required = ("MONGODB_URI", "S3_BUCKET")
    missing = [name for name in required if not os.getenv(name)]
    access_key = os.getenv("S3_ACCESS_KEY_ID") or os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("S3_SECRET_KEY")
    if not access_key or not secret_key:
        missing.append("S3 access credentials")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION", "us-east-1"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    mongo: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.getenv("MONGODB_DATABASE", "aziz_jan_sop")]
    query: dict[str, Any] = {"organization_id": organization_id}
    if source_id:
        query["id"] = source_id
    try:
        sources = await db["source_documents"].find(query).to_list(length=1000)
        print(
            f"organization={organization_id} matching_sources={len(sources)} "
            f"mode={'APPLY' if apply else 'DRY RUN'}"
        )
        for source in sources:
            policy = await db["policies"].find_one(
                {"organization_id": organization_id, "id": source["policy_id"]}
            )
            canonicals = (
                await db["canonical_sops"]
                .find(
                    {
                        "organization_id": organization_id,
                        "policy_id": source["policy_id"],
                        "version_id": source["version_id"],
                    }
                )
                .to_list(length=100)
            )
            explicit_numbers = sorted(
                {
                    section["policy_number"]
                    for canonical in canonicals
                    for section in canonical.get("sections", [])
                    if section.get("policy_number")
                    and re.match(r"^(?:SOP|Policy)\b", section["policy_number"], re.IGNORECASE)
                }
            )
            section_heading_numbers = sorted(
                {
                    number
                    for canonical in canonicals
                    for section in canonical.get("sections", [])
                    for number in _explicit_number.findall(section.get("heading", ""))
                }
            )
            original = probe_object(s3, bucket, organization_id, source["original_artifact_uri"])
            structured = (
                probe_object(s3, bucket, organization_id, source["structured_artifact_uri"])
                if source.get("structured_artifact_uri")
                else None
            )
            old = None
            if source.get("source_format") == "markdown" and original.kind == "pdf":
                candidate = legacy_markdown_uri(source, bucket, organization_id)
                old = probe_object(s3, bucket, organization_id, candidate, hash_text=True)
            category = classify(source, original, structured, old)
            if probe_presigned_preview and original.kind == "pdf":
                print(
                    {
                        "presigned_preview_probe": preview_probe(
                            s3,
                            bucket,
                            object_key(source["original_artifact_uri"], bucket, organization_id),
                        )
                    }
                )
            print(
                {
                    "classification": category,
                    **{
                        key: source.get(key)
                        for key in (
                            "id",
                            "policy_id",
                            "version_id",
                            "file_name",
                            "media_type",
                            "source_format",
                            "original_artifact_uri",
                            "structured_artifact_uri",
                            "structured_file_name",
                            "structured_media_type",
                            "structured_source_format",
                            "status",
                            "parser_provider",
                            "parser_version",
                            "raw_artifact_uri",
                            "error_code",
                        )
                    },
                    "original_probe": original.__dict__,
                    "structured_probe": structured.__dict__ if structured else None,
                    "legacy_markdown_probe": old.__dict__ if old else None,
                    "collection_policy_number": policy.get("policy_number") if policy else None,
                    "section_policy_numbers": explicit_numbers,
                    "canonical_count": len(canonicals),
                    "section_count": sum(len(item.get("sections", [])) for item in canonicals),
                    "section_heading_numbers": section_heading_numbers,
                    "policy_number_repair_candidate": bool(
                        policy
                        and policy.get("policy_number")
                        and len(
                            set(section_heading_numbers)
                            | set(old.heading_policy_numbers if old else ())
                        )
                        > 1
                    ),
                }
            )
            if category != "legacy paired source with mismatched metadata":
                continue
            if (
                not old
                or not old.exists
                or old.kind != "text"
                or old.sha256 != source.get("sha256")
            ):
                print(
                    f"{source['id']}: manual reattachment required; "
                    "verified Markdown artifact unavailable"
                )
                continue
            pdf_name = source["original_artifact_uri"].rsplit("/", 1)[-1]
            if not pdf_name.lower().endswith(".pdf"):
                print(f"{source['id']}: manual review required; PDF filename is ambiguous")
                continue
            updates = {
                "file_name": pdf_name,
                "media_type": "application/pdf",
                "source_format": "pdf",
                "structured_artifact_uri": old.uri,
                "structured_file_name": source["file_name"],
                "structured_media_type": "text/markdown",
                "structured_source_format": "markdown",
            }
            print(f"{source['id']}: verified repair plan={updates}")
            if apply:
                async with mongo.start_session() as session:
                    async with await session.start_transaction():
                        result = await db["source_documents"].update_one(
                            {
                                "_id": source["_id"],
                                "organization_id": organization_id,
                                "original_artifact_uri": original.uri,
                                "structured_artifact_uri": None,
                                "source_format": "markdown",
                                "sha256": old.sha256,
                            },
                            {"$set": updates},
                            session=session,
                        )
                        if result.modified_count != 1:
                            raise RuntimeError("Source changed during inspection; refusing repair")
                        await db["audit_events"].insert_one(
                            {
                                "id": f"audit-{uuid4().hex[:12]}",
                                "organization_id": organization_id,
                                "actor_id": actor_id,
                                "action": "source.legacy_pair_repaired",
                                "entity_type": "source_document",
                                "entity_id": source["id"],
                                "occurred_at": utc_now(),
                                "metadata": {
                                    "original_uri": original.uri,
                                    "structured_uri": old.uri,
                                },
                            },
                            session=session,
                        )
                print(f"{source['id']}: repair applied")
    finally:
        await mongo.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--actor-id", default="legacy-source-repair")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--probe-presigned-preview", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        inspect(
            organization_id=args.organization_id,
            source_id=args.source_id,
            apply=args.apply,
            actor_id=args.actor_id,
            probe_presigned_preview=args.probe_presigned_preview,
        )
    )


if __name__ == "__main__":
    main()
