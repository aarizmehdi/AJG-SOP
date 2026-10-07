import asyncio

from fastapi.testclient import TestClient

from apps.api.app.config import get_settings
from apps.api.app.main import app
from packages.contracts.assistant import Language, MessageRole
from services.assistant.conversation import ConversationTurn
from tests.unit.test_assistant_v2 import PROFILE


async def smoke_test():
    settings = get_settings()
    
    with TestClient(app) as client:
        # The AssistantService is already wired inside app.state because of lifespan
        service = app.state.assistant_service
        profile = PROFILE
        
        print("Running end-to-end API smoke test against real OpenRouter DeepSeek...")
        
        # 1. Normal standalone question
        try:
            response, _ = await service.answer_with_context(
                profile,
                "What is the capacity of the yarn godown?",
                Language.ENGLISH,
                [],
                None
            )
            print("\n[Standalone Question]")
            print("Answer:", response.answer)
            print("Verified:", response.verified)
        except Exception:
            import traceback
            traceback.print_exc()
            return

        # 2. Follow-up / Ambiguous reference
        history = [
            ConversationTurn(role=MessageRole.USER, content="What is the capacity of the yarn godown?"),
            ConversationTurn(role=MessageRole.ASSISTANT, content=response.answer)
        ]
        try:
            response2, _ = await service.answer_with_context(
                profile,
                "Who approves it?",
                Language.ENGLISH,
                history,
                None
            )
            print("\n[Follow-up Question]")
            print("Answer:", response2.answer)
            print("Verified:", response2.verified)
        except Exception:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(smoke_test())
    print("\nSmoke test completed successfully!")
