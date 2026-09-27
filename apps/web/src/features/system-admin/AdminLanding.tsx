import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { profileSchema } from '../../types/profile';

export default function AdminLanding() {
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  if (profile.isPending) return <RouteSkeleton />;
  return (
    <Navigate
      to={
        profile.data?.application_roles.includes('system_admin')
          ? '/admin/overview'
          : '/admin/policies'
      }
      replace
    />
  );
}
