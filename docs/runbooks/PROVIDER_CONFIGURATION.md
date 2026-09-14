# Provider configuration

`APP_MODE=fixture` needs no cloud services. `APP_MODE=live` fails startup when Auth0, Pinecone, or S3 credentials are missing. MongoDB remains the canonical database and S3-compatible storage must be private.

Set `DOCUMENT_PARSER_PROVIDER` to `fixture`, `azure`, `docling`, or `auto`. Azure also requires its endpoint and key. `auto` prefers configured OCR, then optional Docling, then deterministic fixture parsers by format.

Set `LLM_PROVIDER=deepseek`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`, and `DEEPSEEK_MODEL=deepseek-v4-flash`. Put the key only in ignored `.env.local` or a deployment secret store. The assistant adapter makes a non-streaming structured request; verified content is released only after local validation.

Pinecone, S3, Azure, Auth0, and MongoDB adapters are implemented but remain unverified where this environment has no credentials. Never interpret adapter construction as accuracy or readiness evidence.
