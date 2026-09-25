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
