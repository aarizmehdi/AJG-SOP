# ADR 0002: Verified answer release

**Status:** accepted

The assistant retrieves authorized canonical evidence, checks answerability, expands only those authorized chunks within a bounded context budget, and generates a structured candidate. Citation membership, source coordinates, deterministic grounding, and current employee access are checked before release. A malformed or ungrounded candidate may be repaired once; failure after that is a technical error with no candidate text released.

`POST /assistant/answer/events` emits truthful retrieval, reading, generation, repair, and verification stages as they occur. After the **entire** candidate has passed verification and access has been rechecked, it emits `answer_start`, small `answer_delta` chunks, deduplicated `sources`, and `done`. Access is rechecked before each answer delta. Raw DeepSeek tokens never reach the employee.

Conversation turns exist only in the mounted React Assistant page. The client sends at most 16 recent messages per request; the server caps request length and uses prior **user** questions only to form a contextual search query. Previous assistant text is never policy evidence. Each factual turn performs fresh authorized retrieval and verification. No new chat sessions or messages are written to MongoDB, R2, Pinecone, browser storage, or application logs. Historical chat record shapes remain for exact legacy purge compatibility; existing production records are not deleted by this change.
