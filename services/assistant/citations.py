from collections.abc import Sequence

from packages.contracts.assistant import AssistantCitation
from packages.contracts.retrieval import SearchEvidence


class CitationValidator:
    def validate(
        self, citations: Sequence[AssistantCitation], evidence: Sequence[SearchEvidence]
    ) -> bool:
        allowed = {
            (
                item.chunk_id,
                item.policy_id,
                item.policy_title,
                item.section_id,
                item.heading_path,
                item.source.source_document_id,
            ): item
            for item in evidence
        }
        return bool(citations) and all(
            (
                citation.chunk_id,
                citation.policy_id,
                citation.policy_title,
                citation.section_id,
                citation.heading_path,
                citation.document_id,
            )
            in allowed
            and citation.source
            == allowed[
                (
                    citation.chunk_id,
                    citation.policy_id,
                    citation.policy_title,
                    citation.section_id,
                    citation.heading_path,
                    citation.document_id,
                )
            ].source
            for citation in citations
        )
