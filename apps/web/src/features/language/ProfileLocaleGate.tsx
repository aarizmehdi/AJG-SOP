import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { ApiError, apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { profileSchema } from '../../types/profile';
import { useLanguage } from './useLanguage';
import { useFirebaseAuth } from '../auth/firebase-auth-context';

export function ProfileLocaleGate() {
  const { bindProfile, hasPreference, profileId, t } = useLanguage();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { signOut } = useFirebaseAuth();
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });

  useEffect(() => {
    if (profile.data) bindProfile(profile.data);
  }, [bindProfile, profile.data]);

  if (profile.isPending) return <RouteSkeleton />;
  if (profile.isError) {
    const unavailable =
      profile.error instanceof ApiError && profile.error.status === 0;
    const noAccess =
      profile.error instanceof ApiError && profile.error.status === 403;
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          padding: '24px',
        }}
      >
        <ErrorState
          title={t('workspaceUnavailable')}
          detail={
            noAccess
              ? t('accountAccessError')
              : unavailable
                ? t('backendUnavailable')
                : t('workspaceErrorDetail')
          }
        />
        {unavailable ? (
          <button
            className="button button--primary"
            onClick={() => void profile.refetch()}
          >
            {t('retry')}
          </button>
        ) : null}
        {(import.meta.env.VITE_APP_MODE ?? 'fixture') === 'live' ? (
          <button
            onClick={() => {
              queryClient.clear();
              void signOut();
            }}
            style={{
              marginTop: '20px',
              padding: '10px 20px',
              background: '#0284c7',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {t('switchAccount')}
          </button>
        ) : null}
      </div>
    );
  }
  if (profileId !== profile.data.id) return <RouteSkeleton />;
  if (!hasPreference && location.pathname !== '/language')
    return <Navigate to="/language" replace />;
  return <Outlet />;
}
