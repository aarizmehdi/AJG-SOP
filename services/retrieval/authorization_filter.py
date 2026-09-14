from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import EmployeeScope
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.policy import PolicyStatus


class AuthorizationFilter:
    """Produces the only chunk set that candidate retrievers may inspect."""

    def __init__(self, store: FoundationStore) -> None:
        self._store = store

    @staticmethod
    def employee_scope(profile: EmployeeProfile) -> EmployeeScope:
        return EmployeeScope(
            organization_id=profile.organization_id,
            departments=profile.departments,
            locations=profile.locations,
            organizational_roles=profile.organizational_roles,
        )

    def eligible_chunks(self, profile: EmployeeProfile) -> list[RetrievalChunk]:
        scope = self.employee_scope(profile)
        active_version_ids = {
            policy.active_version_id
            for policy in self._store.policies.values()
            if policy.organization_id == profile.organization_id
            and policy.status is PolicyStatus.ACTIVE
            and policy.active_version_id
        }
        return [
            chunk
            for version_id in active_version_ids
            for chunk in self._store.chunks.get(version_id, [])
            if chunk.organization_id == profile.organization_id
            and chunk.version_id == version_id
            and chunk.publication_status == "published"
            and chunk.access.allows(scope)
        ]

    def revalidate(self, profile: EmployeeProfile, chunk: RetrievalChunk) -> bool:
        policy = self._store.policies.get(chunk.policy_id)
        return bool(
            policy
            and policy.organization_id == profile.organization_id
            and policy.status is PolicyStatus.ACTIVE
            and policy.active_version_id == chunk.version_id
            and chunk.organization_id == profile.organization_id
            and chunk.publication_status == "published"
            and chunk.access.allows(self.employee_scope(profile))
        )
