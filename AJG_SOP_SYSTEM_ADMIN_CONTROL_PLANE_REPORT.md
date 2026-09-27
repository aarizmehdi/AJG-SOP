# AJG SOP System Administration Control Plane — Implementation Report

## Delivery identity

- Starting remote `main` SHA: `e7e77f2703dd26846e5ddb31cda0ecb7376fa201`
- Implementation branch: `feat/system-admin-control-plane`
- Final implementation code SHA: `33883faf4944d15bcf8e9f6c80fd5fdf66b39415`
- Pull request: created after this report is committed and the branch is pushed
- Railway deployment: not performed
- Vercel deployment: not performed
- Production data mutation: not performed

The branch was created from the inspected remote `main`. The existing Firebase,
MongoDB, R2, Pinecone E5, DeepSeek, retrieval, ingestion, and publication
architecture was preserved.

## Architecture implemented

### Organization boundary

All control-plane requests derive `organization_id` from the authenticated
MongoDB employee profile. User, catalog, audit, idempotency, and access-inspection
queries inject that trusted tenant boundary. Mutation request models reject extra
fields, including a client-supplied `organization_id`.

System administration remains an organization-level AJT role. No global or
cross-organization administration API was introduced.

### Collections added or changed

- `departments`: stable tenant-owned keys, display name, description, lifecycle,
  optimistic version, and timestamps.
- `locations`: same catalog contract.
- `organizational_roles`: business/job roles, kept separate from application
  roles.
- `employee_profiles`: adds explicit `pending_activation`, `active`, and
  `disabled` membership status, optimistic version, and timestamps while keeping
  the existing `active` field compatible.
- `admin_idempotency`: tenant-scoped create-user request protection.
- `audit_events`: durable tenant-scoped control-plane history, shared with the
  existing policy audit collection.

### Indexes added

- Unique Firebase `identity_subject`.
- Unique `(organization_id, email)` employee membership.
- Employee indexes for tenant plus active state, application roles,
  departments, locations, and organizational roles.
- Unique `(organization_id, key)` and tenant/active indexes for each catalog.
- Unique `(organization_id, key)` admin idempotency index.
- Audit indexes for tenant/time, tenant/actor/time, and tenant/action/time.

### Identity administration

`IdentityAdminService` isolates provider behavior from routes and business
logic. Its official Firebase Admin SDK adapter implements:

- identity creation with an internally generated strong temporary credential;
- disable and refresh-token revocation;
- enable;
- safe delete compensation for an identity created by a failed request;
- password reset-link generation;
- email and display-name update;
- identity lookup.

Passwords, reset links, tokens, service-account data, and API keys are not
stored in MongoDB or audit metadata. Provider errors are converted to safe
product messages. Fixture mode implements the same interface for local tests.

### User lifecycle and role rules

- Searchable, filterable, paginated tenant user list.
- Employee, scoped SOP Administrator, and System Administrator creation.
- Employee scope and SOP-management scope from authoritative catalogs.
- Immediate profile-backed authorization on protected requests.
- One-time activation/reset link response.
- Idempotent create-user requests.
- Firebase/Mongo compensation on partial failures.
- Profile and identity editing with optimistic concurrency.
- Disable at both identity and membership layers.
- Reactivation after identity and catalog validation.
- Password-reset initiation without password retrieval.
- First successful authenticated request completes `pending_activation`.
- Every role set includes `employee`; `system_admin` also includes `sop_admin`.
- Only a System Administrator route can grant `system_admin`.
- The final active System Administrator cannot be disabled or demoted.
- Removing one's own System Administrator role requires explicit confirmation.
- Disabling one's own account requires an exact email confirmation.

### Organization catalogs

System Administrators can create, rename, describe, deactivate, and reactivate
departments, locations, and organizational roles. Stable keys are immutable.
Deactivation is blocked while a key is referenced by active employees, SOP
Administrator management scopes, or active/published policy versions.

New assignments require active catalog values. Existing inactive values remain
readable and can remain on historical user or policy records, but cannot be
newly assigned.

### SOP access integration

The Add SOP and policy-access editor now load organization catalogs instead of
accepting free-text strings. They retain explicit `All` versus `Selected`
controls. The API independently validates all selected keys and continues to
enforce SOP Administrator management boundaries.

Employee search, policy reading, and assistant requests still use the existing
authorization and retrieval services. No authorization decision was delegated
to the LLM, and the RAG provider stack was not changed.

### Audit actions introduced

- `organization.department_created|updated|deactivated|reactivated`
- `organization.location_created|updated|deactivated|reactivated`
- `organization.organizational_role_created|updated|deactivated|reactivated`
- `identity.user_created|updated|activated|disabled|reactivated`
- `identity.password_reset_generated`
- `access.application_roles_changed`
- `access.employee_scope_changed`
- `access.management_scope_changed`
- `access.system_admin_granted|removed`

Audit APIs are read-only and System Administrator-only. The UI supports actor,
action, entity, affected user, and date filters.

## Product surfaces delivered

- `/admin/overview`
- `/admin/users`
- `/admin/users/new`
- `/admin/users/:userId`
- `/admin/departments`
- `/admin/locations`
- `/admin/organizational-roles`
- `/admin/access`
- `/admin/audit`
- `/admin/organization`

The administration shell shows System Administrator navigation only to System
Administrators. SOP Administrators retain their scoped knowledge workflows.
Employee accounts receive no administration controls. Loading, empty, error,
inactive, pending, success, and confirmation states are implemented. Desktop
and mobile views were inspected in the local fixture application; no browser
console errors were observed.

## Migration and bootstrap

No production migration was run. The non-destructive bootstrap tool is:

```powershell
uv run python scripts/seed/bootstrap_organization_catalogs.py --organization-id ajt
```

Dry-run is the default. It inspects existing employee scopes, management scopes,
and policy access scopes; preserves exact legacy keys; reports missing catalog
records; and reports profiles needing lifecycle fields. After review, apply with
an existing System Administrator profile id:

```powershell
uv run python scripts/seed/bootstrap_organization_catalogs.py --organization-id ajt --apply --actor-id <system-admin-profile-id>
```

The existing provisioning scripts remain available as bootstrap or break-glass
tools. They are no longer the intended daily user-management path after the
control plane is deployed and accepted.

## Verification results

- Ruff: passed.
- MyPy strict mode: passed for 87 source files.
- Backend tests: 70 passed.
- Backend security and integration tests: passed.
- TypeScript project build: passed.
- ESLint: passed with zero warnings.
- Prettier: passed.
- Frontend tests: 19 passed across 12 files.
- Vite production build: passed; one existing-style bundle-size advisory remains
  for the 554.25 kB main chunk.
- Credential-pattern scan of tracked file contents: passed.
- `git diff --check`: passed.
- Local fixture API/UI smoke test: passed for overview, users, create-user,
  catalog, desktop, tablet, and mobile rendering.
- Docker build: not run because the `docker` executable is unavailable on this
  host.

Tests cover anonymous access, unknown fixture identity, Employee and SOP Admin
denial, direct HTTP privilege-escalation attempts, rejected client tenant ids,
cross-tenant lookup, manipulated catalog keys, stable-key rename behavior,
referenced-catalog protection, inactive historical values, idempotent creation,
duplicate Firebase email, Firebase-success/Mongo-failure compensation, retry
after partial failure, Firebase-disable failure, Mongo-disable failure with
identity re-enable, stale-session membership denial, last-admin safeguards, and
role-aware frontend navigation.

## Fixture versus live-provider status

The complete acceptance path was exercised with local fixture identities,
catalogs, Mongo-compatible in-memory persistence, canonical Markdown ingestion,
publication, retrieval, and UI surfaces.

No live Firebase Admin, MongoDB Atlas mutation, Railway deployment, Vercel
deployment, or controlled production acceptance user was created during this
milestone. No live-provider success is claimed. Pinecone E5, DeepSeek, R2, and
the existing production RAG path were deliberately left unchanged.

## Rollback procedure

Before production mutation:

1. retain the current Railway and Vercel deployment revisions;
2. run and archive the bootstrap dry-run report;
3. confirm the current active System Administrator profiles and Firebase UIDs;
4. export or otherwise snapshot the affected MongoDB collections using the
   organization's existing operational process.

If application deployment fails, restore the previous Railway and Vercel
revisions. The schema changes are additive and legacy profiles remain readable.
Catalog bootstrap creates stable reference records and backfills lifecycle
fields; it does not delete or rename existing scope values. Preserve audit
records. If a newly created identity is left inconsistent, disable that exact
Firebase UID, reconcile its tenant profile, and record the operational action.

## Known limitations and verdict

- Production catalog bootstrap still requires reviewed execution.
- Live Firebase/Mongo orchestration and provider failure behavior still require
  controlled production validation with configured credentials.
- The complete PRD acceptance scenario, including two controlled production
  employees, scoped SOP publication, Pinecone retrieval, and DeepSeek answer,
  has not been executed on production.
- Docker image validation remains pending on a host with Docker available.
- Automated organizational email delivery is not implemented; the System
  Administrator receives the one-time Firebase reset/setup link for delivery
  through an approved private channel.

**Verdict: Not Ready for controlled AJT production use until the reviewed
bootstrap, deployment smoke tests, Docker/CI validation, and full controlled
acceptance scenario are completed.**
