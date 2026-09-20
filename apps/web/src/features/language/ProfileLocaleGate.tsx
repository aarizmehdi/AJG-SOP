import { useAuth0 } from '@auth0/auth0-react';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { profileSchema } from '../../types/profile';
import { useLanguage } from './useLanguage';

export function ProfileLocaleGate() {
  const { bindProfile, hasPreference, profileId, t } = useLanguage();
  const location = useLocation();
  const { logout } = useAuth0();
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });

  useEffect(() => {
    if (profile.data) bindProfile(profile.data);
  }, [bindProfile, profile.data]);

  if (profile.isPending) return <RouteSkeleton />;
  if (profile.isError)
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
            profile.error.message
              ? `${t('workspaceErrorDetail')} (${profile.error.message})`
              : t('workspaceErrorDetail')
          }
        />
        {(import.meta.env.VITE_APP_MODE ?? 'fixture') === 'live' ? (
          <button
            onClick={() => {
              void logout({
                logoutParams: { returnTo: `${window.location.origin}/login` },
              });
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
            Sign Out &amp; Switch Account
          </button>
        ) : null}
      </div>
    );
  if (profileId !== profile.data.id) return <RouteSkeleton />;
  if (!hasPreference && location.pathname !== '/language')
    return <Navigate to="/language" replace />;
  return <Outlet />;
}
