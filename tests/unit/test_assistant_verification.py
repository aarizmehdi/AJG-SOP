from collections.abc import Sequence

import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.assistant import AssistantCitation, GeneratedAnswer
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import SearchEvidence
from services.assistant.answer_generator import LLMProvider
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.grounding import GroundingVerifier


def evidence() -> SearchEvidence:
    return SearchEvidence(
        organization_id="ajt",
        chunk_id="allowed-chunk",
        policy_id="policy",
        version_id="version",
        section_id="section",
        policy_title="Policy",
        heading_path=("Policy", "Section"),
        excerpt="Report damaged stock within 12 hours.",
        source=SourceLocator(source_document_id="document", page_start=4, page_end=4),
        fused_score=1,
    )


class StubRetrieval:
    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]:
        return [evidence()]


class InventedCitationProvider(LLMProvider):
    provider_id = "test"
    model_id = "test"

    async def generate(
        self, question: str, items: Sequence[SearchEvidence], language: Language
    ) -> GeneratedAnswer:
        item = items[0]
        return GeneratedAnswer(
            answerable=True,
            answer="Report damaged stock within 12 hours.",
            citations=[
                AssistantCitation(
                    chunk_id="invented",
                    policy_id=item.policy_id,
                    policy_title=item.policy_title,
                    section_id=item.section_id,
                    heading_path=item.heading_path,
                    document_id=item.source.source_document_id,
                    source=item.source,
                )
            ],
        )


@pytest.mark.asyncio
async def test_invented_citation_prevents_answer_release() -> None:
    profile = EmployeeProfile(
        id="employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )
    store = FoundationStore()
    service = AssistantService(
        store,
        StubRetrieval(),
        FixtureAnswerabilityGate(),
        InventedCitationProvider(),
        CitationValidator(),
        GroundingVerifier(),
    )

    with pytest.raises(VerificationError):
        await service.answer(profile, "When?", Language.ENGLISH)

    assert all(message.role.value != "assistant" for message in store.chat_messages)
