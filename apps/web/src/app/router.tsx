import { Suspense } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { RouteSkeleton } from '../components/feedback/RouteSkeleton';
import { AuthGuard } from '../features/auth/AuthGuard';
import { ProfileLocaleGate } from '../features/language/ProfileLocaleGate';
import {
  AddSOP,
  AdminLanding,
  AvailablePolicies,
  AccessInspector,
  Admin,
  AdminLibrary,
  AdminPolicyDetail,
  Assistant,
  AuditLog,
  CreateUser,
  Departments,
  ExtractionReview,
  Home,
  Language,
  Locations,
  Login,
  Policy,
  PolicyWorkflow,
  OrganizationalRoles,
  OrganizationSettings,
  Search,
  SystemAdminOverview,
  UserDetail,
  UserList,
} from './routeModules';

import { RootRedirect } from './RootRedirect';

const loading = (node: React.ReactNode) => (
  <Suspense fallback={<RouteSkeleton />}>{node}</Suspense>
);

export const router = createBrowserRouter([
  { path: '/', element: <RootRedirect /> },
  { path: '/login', element: loading(<Login />) },
  {
    element: (
      <AuthGuard>
        <ProfileLocaleGate />
      </AuthGuard>
    ),
    children: [
      { path: '/language', element: loading(<Language />) },
      {
        element: <AppShell />,
        children: [
          { path: '/home', element: loading(<Home />) },
          { path: '/search', element: loading(<Search />) },
          { path: '/assistant', element: loading(<Assistant />) },
          { path: '/policies/:policyId', element: loading(<Policy />) },
          { path: '/policies', element: loading(<AvailablePolicies />) },
          {
            path: '/admin',
            element: loading(<Admin />),
            children: [
              {
                index: true,
                element: loading(<AdminLanding />),
              },
              { path: 'overview', element: loading(<SystemAdminOverview />) },
              { path: 'users', element: loading(<UserList />) },
              { path: 'users/new', element: loading(<CreateUser />) },
              { path: 'users/:userId', element: loading(<UserDetail />) },
              { path: 'departments', element: loading(<Departments />) },
              { path: 'locations', element: loading(<Locations />) },
              {
                path: 'organizational-roles',
                element: loading(<OrganizationalRoles />),
              },
              { path: 'access', element: loading(<AccessInspector />) },
              { path: 'audit', element: loading(<AuditLog />) },
              {
                path: 'organization',
                element: loading(<OrganizationSettings />),
              },
              {
                path: 'policies',
                element: loading(<AdminLibrary key="library" />),
              },
              {
                path: 'review-queue',
                element: loading(<AdminLibrary key="review-queue" />),
              },
              { path: 'add', element: loading(<AddSOP />) },
              {
                path: 'review/:sourceId',
                element: loading(<ExtractionReview />),
              },
              {
                path: 'policies/:policyId',
                element: loading(<AdminPolicyDetail />),
              },
              {
                path: 'workflow/:policyId',
                element: loading(<PolicyWorkflow />),
              },
            ],
          },
        ],
      },
    ],
  },
]);
