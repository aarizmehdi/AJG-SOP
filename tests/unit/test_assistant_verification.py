from collections.abc import Sequence

import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from packages.contracts.assistant import AssistantCitation, GeneratedAnswer
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
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
    async def assistant_context(self, profile, evidence):
        return [AssistantEvidence(**item.model_dump(), full_text=item.excerpt) for item in evidence]

    async def revalidate_evidence(self, profile, evidence):
        return True

    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]:
        return [evidence()]


class InventedCitationProvider(LLMProvider):
    provider_id = "test"
    model_id = "test"

    async def generate(
        self,
        question: str,
        items: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
        **kwargs,
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

    async def plan_query(self, *args, **kwargs):
        from packages.contracts.assistant import QueryPlan, InternalAnswerMode
        return QueryPlan(
            resolved_query="test",
            is_follow_up=False,
            answer_mode=InternalAnswerMode.ANSWER
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
    service = AssistantService(
        StubRetrieval(),
        FixtureAnswerabilityGate(),
        InventedCitationProvider(),
        CitationValidator(),
        GroundingVerifier(),
    )

    with pytest.raises(VerificationError):
        await service.answer(profile, "When must damaged stock be reported?", Language.ENGLISH)
