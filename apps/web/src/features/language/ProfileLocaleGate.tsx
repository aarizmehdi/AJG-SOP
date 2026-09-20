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
      <ErrorState
        title={t('workspaceUnavailable')}
        detail={
          (profile.error as Error)?.message
            ? `${t('workspaceErrorDetail')} (${(profile.error as Error).message})`
            : t('workspaceErrorDetail')
        }
      />
    );
  if (profileId !== profile.data.id) return <RouteSkeleton />;
  if (!hasPreference && location.pathname !== '/language')
    return <Navigate to="/language" replace />;
  return <Outlet />;
}
