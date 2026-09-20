import { Navigate } from 'react-router-dom';
import { RouteSkeleton } from '../components/feedback/RouteSkeleton';
import { useFirebaseAuth } from '../features/auth/firebase-auth-context';

function LiveRootRedirect() {
  const { authenticated, initialized } = useFirebaseAuth();
  if (!initialized) return <RouteSkeleton />;
  if (authenticated) {
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
