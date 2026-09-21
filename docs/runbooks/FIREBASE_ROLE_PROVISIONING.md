# Firebase Employee and SOP Admin provisioning

This runbook provisions two pre-existing Firebase Authentication users into MongoDB. Firebase proves identity; MongoDB remains the only source for organization, application roles, employee scope, and management scope. The API never creates a profile during login.

## Assigned production scopes

| Profile | Application roles | Employee department/location/role | Management scope |
| --- | --- | --- | --- |
| Employee | `employee` | `operations` / `head-office` / `employee` | None |
| SOP Admin | `employee`, `sop_admin` | `operations` / `head-office` / `manager` | `operations` / `head-office` / `employee` or `manager` |

The SOP Admin can read the admin policy library and manage only explicit selected scopes contained by all three management dimensions. The account cannot create/upload SOPs, change access, retry ingestion, or use other System Admin-only endpoints.

## Production activation

1. In Firebase Authentication, confirm both users are enabled and send each user an email-verification link. Both current accounts exist and are enabled, but their email addresses are not yet verified.
2. Run the guarded script from the repository with Railway production variables. Do not copy the MongoDB URI or service-account JSON into the command or a local file.

   ```bash
   railway run --no-local -- uv run python -m scripts.identity.provision_role_profiles \
     --employee-uid "C0cQBRVbK2cnArZNYhyZK4qqOl02" \
     --sop-admin-uid "3rXmVfp7ByP7atAtYqgVtjnl9Ps1"
   ```

3. Review the dry-run result. It must report two verified, enabled Firebase users, organization `ajt`, no collisions, and two profiles to create.
4. Apply the same exact plan:

   ```bash
   railway run --no-local -- uv run python -m scripts.identity.provision_role_profiles \
     --employee-uid "C0cQBRVbK2cnArZNYhyZK4qqOl02" \
     --sop-admin-uid "3rXmVfp7ByP7atAtYqgVtjnl9Ps1" \
     --apply
   ```

5. Ask each user to complete Firebase email verification, then sign in at the production login page. Existing passwords remain in Firebase and are never handled by this script.
6. Confirm `GET /api/v1/profile/me` returns organization `ajt` and the exact assigned roles for each account.
7. Confirm the Employee receives `403` from `GET /api/v1/admin/policies`.
8. Confirm the SOP Admin receives `200` from `GET /api/v1/admin/policies` and `403` from `GET /api/v1/admin/sources/capabilities`.

The script is idempotent only when existing records exactly match the approved plan. Any UID, profile ID, email, role, organization, or scope collision stops the transaction. Applying it inserts only the two new profiles and matching audit events; it never updates an existing profile or grants `system_admin`.
