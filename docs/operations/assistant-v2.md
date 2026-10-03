# AJG SOP Assistant v2 operations

The Assistant uses the existing published-policy retrieval service. Search excerpts remain short; generation expands only the selected, currently authorized chunks to at most 5,000 characters each and 16,000 characters total. Retrieval authorization, lexical/semantic fusion, publication state, and source-file rules remain unchanged.

`LLM_PROVIDER=deepseek` selects the DeepSeek adapter. Configure `DEEPSEEK_API_KEY` as a Railway secret; `DEEPSEEK_MODEL` defaults to `deepseek-flash` and `DEEPSEEK_TEMPERATURE` defaults to `0.2`. Fixture tests use `LLM_PROVIDER=fixture` and make no live-provider accuracy claim. If DeepSeek is unavailable, employee search and policy reading remain usable.

The authenticated `POST /api/v1/assistant/answer/events` accepts `question`, `language`, and up to 16 bounded `history` turns. It sends event-stream `status` events during real work, then `answer_start`, verified `answer_delta`, `sources`, and `done`. A technical failure yields `error` without model text. The JSON `/answer` endpoint remains available for clients that cannot stream. `smalltalk`, `clarification`, `out_of_scope`, and `no_answer` are normal verified responses with no citations; only grounded `policy_answer` contains citations.

Metrics expose retrieval, LLM, grounding verification, total assistant work, response kind, repair count, first status, first verified delta, and completed stream latency. They contain no question or answer text. Retrieval traces contain query length and chunk IDs, not raw queries. Existing historical Mongo `chat_sessions` and `chat_messages` are left untouched; Assistant v2 neither loads nor writes them.

Before a production rollout, benchmark real AJG SOP examples in English, Urdu, and Roman Urdu for answerability, citation precision, grounding, long-section context, ambiguous follow-ups, latency, and false rejections. The fixture provider and deterministic verifier do not establish real-document or live DeepSeek quality. Review monitoring for provider errors and verification failures without logging employee conversation text.
