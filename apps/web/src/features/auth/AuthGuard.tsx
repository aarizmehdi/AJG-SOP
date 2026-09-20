import { useAuth0 } from '@auth0/auth0-react';
import type { PropsWithChildren } from 'react';
import { Navigate } from 'react-router-dom';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';

function LiveAuthGuard({ children }: PropsWithChildren) {
  const { isAuthenticated, isLoading, error } = useAuth0();
  if (isLoading) return <RouteSkeleton />;
  if (error) {
    return (
      <div
        style={{
          padding: '24px',
          maxWidth: '560px',
          margin: '60px auto',
          background: '#fef2f2',
          border: '1px solid #fca5a5',
          borderRadius: '12px',
          color: '#991b1b',
          fontFamily: 'sans-serif',
        }}
      >
        <h2 style={{ marginTop: 0, fontSize: '20px' }}>Authentication Error</h2>
        <p style={{ fontSize: '14px', lineHeight: '1.5', wordBreak: 'break-word' }}>
          {error.message}
        </p>
        <button
          onClick={() => {
            window.location.href = '/login';
          }}
          style={{
            padding: '10px 18px',
            background: '#991b1b',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Return to Login
        </button>
      </div>
    );
  }
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
