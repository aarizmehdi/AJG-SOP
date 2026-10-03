# Permanent policy purge

System Administrators can preview and permanently delete a policy from its detail page's Danger Zone. Employees and SOP Administrators receive 403. Foreign-organization policy IDs receive 404. Archive remains reversible and separate.

GET `/api/v1/admin/policies/{policy_id}/purge-preview` discovers all versions, attached and orphaned sources, canonical documents, raw parser results, ingestion jobs, chunks, and exact structured references in every Mongo collection. It inventories every object under `{organization_id}/sources/{source_id}/` and lists/fetches every Pinecone namespace page. It performs no production writes. Conflicting ownership, unscoped linked records, protected catalog/profile references, and source URIs outside their exact source prefix block deletion.

POST `/api/v1/admin/policies/{policy_id}/purge` accepts only `title`, `phrase`, and `preview_token`. The server independently verifies System Admin membership, tenant, exact title, `DELETE PERMANENTLY`, and the current inventory fingerprint. The server discovers all resource IDs. Preview changes require a new preview.

A durable `policy_purges` operation is recorded before external deletion. All application workers evict marked policies from the FoundationStore and pending mutations on startup and before requests; retrieval checks the marker again before selecting evidence and releasing a generated answer. Linked runtime retrieval traces are removed. Normal foundation flush remains upsert-only. Application mutation requests, shutdown flushes, and the maintenance CLI share a renewable Mongo write lease. Lease renewal failure cancels the protected operation. Do not run old application revisions or unsupported writers alongside a purge.

Stages are Pinecone deletion/verification, exact R2 prefix deletion/verification, Mongo cascade, and final cross-provider verification. Failures keep the policy blocked and retain a minimal retry manifest with resource IDs, original confirmation preview and stage counts. Retrying resumes unfinished stages and safely handles already removed resources. Successful completion removes the entire temporary operation manifest. Only one minimal `policy.purged` audit event remains per policy, with organization ID, deleted policy ID, actor, timestamp and aggregate counts. That event also serves as the durable cache-invalidation marker. It contains no SOP content, filename, title, confirmation hash or signed URL. A completed retry is a no-op that returns the existing audit counts after System Admin and phrase validation; no title is retained solely to validate a no-op.

Pinecone deletion enumerates all records, including unknown/stale versions identified by exact policy metadata, and deletes bounded ID batches. Verification requires two consecutive empty full namespace inventories for the policy; a top-k query is not proof. The existing index, dimensions, namespace prefix and credentials are preserved.

Chat messages currently store answer text without structured citation provenance. Exact linked rows are removed if relationships exist, but historical text cannot be deterministically attributed to a policy. It is retained rather than deleting unrelated conversations by prose matching. Previously downloaded files cannot be recalled. S3/R2 deletion uses object deletion; providers with object versioning enabled need a separate approved version-purge extension.

## Authorized AJG test cleanup

The task-specific maintenance entry point uses the same service and adapters as the API. It verifies an existing active AJG System Admin against Firebase and explicitly checks the two approved policy IDs, titles, and source filenames. It never creates users or changes privileges. Default mode is read-only and writes an inventory file locally:

```powershell
npx --yes @railway/cli run --no-local -- uv run python -m scripts.purge.ajt_test_policies --inventory .data/purge-production-preview.json
```

Apply is authorized only for the two test uploads named in that tool. Deploy the tested backend first, verify its preview route returns 401 without authentication, and ensure the old deployment has stopped. Freeze supported writers through the lease and validate both previews before the first deletion:

```powershell
npx --yes @railway/cli run --no-local -- uv run python -m scripts.purge.ajt_test_policies --inventory .data/purge-production-preview.json --apply
npx --yes @railway/cli run --no-local -- uv run python -m scripts.purge.ajt_test_policies --inventory .data/purge-production-preview.json --verify
```

Any extra policy, title/source mismatch or changed inventory aborts apply. Preserve the local inventory until verification has finished. It contains resource IDs and counts, not credentials. Normal product purge uses the authenticated API; this maintenance tool deliberately refuses arbitrary production batch selection.

After cleanup, verify authenticated admin library/viewers/review sources, employee policy list/readers, Search and Assistant for all relevant accounts. Empty search must return no evidence; assistant must return unanswerable with no citations without requiring an LLM call. Verify catalogs, organization, user profiles and Firebase identities remain intact. Do not upload test content to production as part of verification.
