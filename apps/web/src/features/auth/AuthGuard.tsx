import { useAuth0 } from '@auth0/auth0-react';
import type { PropsWithChildren } from 'react';
import { Navigate } from 'react-router-dom';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';

function LiveAuthGuard({ children }: PropsWithChildren) {
  const { isAuthenticated, isLoading } = useAuth0();
  if (isLoading) return <RouteSkeleton />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

export function AuthGuard({ children }: PropsWithChildren) {
  if ((import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture') {
    const identity = window.localStorage.getItem('ajt-fixture-identity');
    if (!identity) return <Navigate to="/login" replace />;
    return children;
  }
  return <LiveAuthGuard>{children}</LiveAuthGuard>;
}
