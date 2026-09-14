from abc import ABC, abstractmethod

from packages.contracts.canonical import BlockKind, CanonicalSOP, RetrievalChunk


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        raise NotImplementedError


class SectionAwareFixtureChunker(Chunker):
    """One coherent section per chunk; size and overlap remain intentionally provisional."""

    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        chunks: list[RetrievalChunk] = []
        for index, section in enumerate(document.sections):
            text_parts = [" > ".join(section.heading_path)]
            for block in section.blocks:
                if block.text:
                    text_parts.append(block.text)
                elif block.list_items:
                    text_parts.extend(item.text for item in block.list_items)
                elif block.kind is BlockKind.TABLE and block.table:
                    text_parts.extend(cell.text for cell in block.table.cells)
            chunks.append(
                RetrievalChunk(
                    id=f"{document.version_id}:{section.id}:0",
                    organization_id=document.organization_id,
                    policy_id=document.policy_id,
                    version_id=document.version_id,
                    source_document_id=section.source.source_document_id,
                    section_id=section.id,
                    parent_section_id=section.parent_section_id,
                    heading_path=section.heading_path,
                    policy_number=section.policy_number,
                    text="\n".join(text_parts),
                    access=section.access,
                    source=section.source,
                    chunk_index=index,
                    publication_status=publication_status,
                )
            )
        return chunks
