# Incident response

For suspected cross-tenant or unauthorized retrieval, disable employee retrieval, preserve audit and retrieval traces, rotate affected service credentials, identify the active version and organization, and reproduce with the exact employee scope. Do not expose source content in incident tickets.

For ingestion failure, inspect the tenant-scoped job events and parser capability, preserve the original, correct provider configuration, then use the retry endpoint. Do not publish until human approval and index verification complete.

For Pinecone failure, keep the current published version reference unchanged and rebuild derived data from Mongo canonical chunks. For LLM failure, keep search and canonical policy reading available. For grounding failure, withhold the candidate answer and investigate only through protected logs and metrics.
