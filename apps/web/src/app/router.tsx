import { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { RouteSkeleton } from '../components/feedback/RouteSkeleton';
import { AuthGuard } from '../features/auth/AuthGuard';
import { ProfileLocaleGate } from '../features/language/ProfileLocaleGate';
import {
  AddSOP,
  Admin,
  AdminLibrary,
  AdminPolicyDetail,
  Assistant,
  ExtractionReview,
  Home,
  Language,
  Login,
  Policy,
  PolicyWorkflow,
  Search,
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
          {
            path: '/admin',
            element: loading(<Admin />),
            children: [
              {
                index: true,
                element: <Navigate to="/admin/policies" replace />,
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
