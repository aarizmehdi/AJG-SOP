import { lazy } from 'react';

export const Login = lazy(() => import('../features/auth/LoginPage'));
export const Language = lazy(() => import('../features/language/LanguagePage'));
export const Home = lazy(() => import('../features/home/HomePage'));
export const Search = lazy(() => import('../features/search/SearchPage'));
export const Assistant = lazy(
  () => import('../features/assistant/AssistantPage'),
);
export const Policy = lazy(() => import('../features/policies/PolicyPage'));
export const AvailablePolicies = lazy(
  () => import('../features/policies/AvailablePoliciesPage'),
);
export const Admin = lazy(() => import('../features/admin/AdminPage'));
export const AdminLibrary = lazy(
  () => import('../features/admin/AdminLibraryPage'),
);
export const AdminPolicyDetail = lazy(
  () => import('../features/admin/AdminPolicyDetailPage'),
);
export const AddSOP = lazy(() => import('../features/admin/AddSOPPage'));
export const ExtractionReview = lazy(
  () => import('../features/admin/ExtractionReviewPage'),
);
export const PolicyWorkflow = lazy(
  () => import('../features/admin/PolicyWorkflowPage'),
);
export const AdminLanding = lazy(
  () => import('../features/system-admin/AdminLanding'),
);
export const SystemAdminOverview = lazy(
  () => import('../features/system-admin/SystemAdminOverviewPage'),
);
export const UserList = lazy(
  () => import('../features/system-admin/users/UserListPage'),
);
export const CreateUser = lazy(
  () => import('../features/system-admin/users/CreateUserPage'),
);
export const UserDetail = lazy(
  () => import('../features/system-admin/users/UserDetailPage'),
);
export const Departments = lazy(
  () => import('../features/system-admin/organization/DepartmentsPage'),
);
export const Locations = lazy(
  () => import('../features/system-admin/organization/LocationsPage'),
);
export const OrganizationalRoles = lazy(
  () => import('../features/system-admin/organization/OrganizationalRolesPage'),
);
export const OrganizationSettings = lazy(
  () =>
    import('../features/system-admin/organization/OrganizationSettingsPage'),
);
export const AccessInspector = lazy(
  () => import('../features/system-admin/access/AccessInspectorPage'),
);
export const AuditLog = lazy(
  () => import('../features/system-admin/audit/AuditLogPage'),
);
