import { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { RouteSkeleton } from '../components/feedback/RouteSkeleton';
import { AuthGuard } from '../features/auth/AuthGuard';
import {
  AddSOP,
  Admin,
  AdminLibrary,
  Assistant,
  ExtractionReview,
  Home,
  Language,
  Login,
  Policy,
  PolicyWorkflow,
  Search,
} from './routeModules';

const loading = (node: React.ReactNode) => (
  <Suspense fallback={<RouteSkeleton />}>{node}</Suspense>
);

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/home" replace /> },
  { path: '/login', element: loading(<Login />) },
  { path: '/language', element: loading(<Language />) },
  {
    element: (
      <AuthGuard>
        <AppShell />
      </AuthGuard>
    ),
    children: [
      { path: '/home', element: loading(<Home />) },
      { path: '/search', element: loading(<Search />) },
      { path: '/assistant', element: loading(<Assistant />) },
      { path: '/policies/:policyId', element: loading(<Policy />) },
      {
        path: '/admin',
        element: loading(<Admin />),
        children: [
          { index: true, element: loading(<AdminLibrary />) },
          { path: 'add', element: loading(<AddSOP />) },
          { path: 'review/:sourceId', element: loading(<ExtractionReview />) },
          { path: 'policies/:policyId', element: loading(<PolicyWorkflow />) },
        ],
      },
    ],
  },
]);
