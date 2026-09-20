import { useAuth0 } from '@auth0/auth0-react';
import { Navigate } from 'react-router-dom';
import { RouteSkeleton } from '../components/feedback/RouteSkeleton';

function LiveRootRedirect() {
  const { isAuthenticated, isLoading } = useAuth0();
  const search = window.location.search;
  const hasAuthCodeOrError =
    search.includes('code=') || search.includes('error=');

  if (isLoading || hasAuthCodeOrError) {
    return <RouteSkeleton />;
  }
  if (isAuthenticated) {
    return <Navigate to="/home" replace />;
  }
  return <Navigate to="/login" replace />;
}

export function RootRedirect() {
  if ((import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture') {
    return <Navigate to="/home" replace />;
  }
  return <LiveRootRedirect />;
}
