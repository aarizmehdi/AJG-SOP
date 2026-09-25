# Provider configuration

`APP_MODE=fixture` needs no cloud services. `APP_MODE=live` fails startup when Firebase Admin, Pinecone, or S3 credentials are missing. MongoDB remains the canonical database and S3-compatible storage must be private.

Set `DOCUMENT_PARSER_PROVIDER` to `fixture`, `azure`, `docling`, or `auto`. Azure also requires its endpoint and key. `auto` prefers configured OCR, then optional Docling, then deterministic fixture parsers by format.

Set `LLM_PROVIDER=deepseek`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`, and `DEEPSEEK_MODEL=deepseek-flash`. Put the key only in ignored `.env.local` or a deployment secret store. The assistant adapter makes a non-streaming structured request; verified content is released only after local validation. The model identifier was verified through the provider's authenticated `/models` endpoint on 2026-09-25.

Production embeddings use `EMBEDDING_PROVIDER=pinecone_e5` and `EMBEDDING_MODEL=multilingual-e5-large`. The existing `aziz-jan-sop` managed index is configured for Pinecone-hosted integrated inference with passage writes, query reads, cosine similarity, and 1024-dimensional vectors. Startup validates that the configured model and returned vector dimension match the existing index. Fixture mode remains deterministic and never calls Pinecone.

Pinecone is derived retrieval storage. MongoDB remains canonical. Never create or reconfigure an index from application startup, and never silently substitute fixture embeddings in live mode.

## Speech input

Speech is disabled by default. The backend exposes a provider-neutral `SpeechToTextProvider`
contract whose result contains the detected language, raw transcript, and transcript normalized to
the employee's selected product language. `SPEECH_PROVIDER=disabled` installs an unavailable
provider and returns a deliberate service-unavailable response; it never invents a transcript.

Keep `VITE_VOICE_INPUT_ENABLED=false` until a production provider has been implemented, configured,
and validated for English, Urdu, code switching, and Roman Urdu normalization. When enabled, the
browser requests microphone access only after the employee activates the microphone. Cancelled
recordings are discarded, and successful transcripts are placed in the composer for review rather
than submitted automatically. Audio and transcripts are not persisted by this foundation.

## Deployment targets

The frontend is a Vite single-page application deployed from `apps/web` to Vercel; `vercel.json`
provides the history fallback. The API remains a Railway target. Both production services should
track `main` after the branch is verified. Cloudflare R2 remains the private S3-compatible artifact
store and is independent of frontend hosting.
