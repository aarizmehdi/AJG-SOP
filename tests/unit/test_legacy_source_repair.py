from io import BytesIO

from scripts.source.inspect_legacy_pairs import (
    Probe,
    classify,
    heading_policy_numbers,
    probe_object,
)


class RangeOnlyS3:
    def __init__(self) -> None:
        self.requests: list[str | None] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "private"
        assert Key == "ajt/sources/source/original.pdf"
        return {"ContentLength": 22_622_995, "ContentType": "application/pdf"}

    def get_object(self, *, Bucket: str, Key: str, Range: str | None = None) -> dict[str, BytesIO]:
        self.requests.append(Range)
        assert Range == "bytes=0-31"
        return {"Body": BytesIO(b"%PDF-1.7" + b" " * 24)}


def test_large_pdf_probe_reads_only_signature() -> None:
    s3 = RangeOnlyS3()
    result = probe_object(s3, "private", "ajt", "s3://private/ajt/sources/source/original.pdf")
    assert result.kind == "pdf"
    assert result.size == 22_622_995
    assert s3.requests == ["bytes=0-31"]


def test_legacy_mismatch_and_missing_artifact_are_distinct() -> None:
    original = Probe("s3://private/ajt/original.pdf", True, "pdf", 22_622_995, "application/pdf")
    structured = Probe("s3://private/ajt/original.md", True, "text", 57_007, "text/markdown")
    metadata = {"source_format": "markdown"}
    assert classify(metadata, original, None, structured) == (
        "legacy paired source with mismatched metadata"
    )
    assert classify(metadata, original, structured, None) == "correct new PDF + Markdown pair"
    assert classify(metadata, Probe("missing", False, "missing", None, None), None, None) == (
        "corrupted/missing artifact"
    )


def test_multi_sop_legacy_markdown_can_be_flagged_without_changing_it() -> None:
    numbers = heading_policy_numbers(
        "# Store collection\n## SOP # 25 — Dispatch\nText referring to SOP #99.\n"
        "## SOP # 26 — Receipt\n"
    )
    assert numbers == ("25", "26")
