import { Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { profileSchema } from '../../types/profile';
import { useAdminCopy } from './adminCopy';

export default function AdminPage() {
  const { copy } = useAdminCopy();
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  if (profile.isPending) return <RouteSkeleton label={copy.loadingSops} />;
  if (
    profile.isError ||
    !profile.data.application_roles.some(
      (role) => role === 'sop_admin' || role === 'system_admin',
    )
  )
    return (
      <main className="page">
        <ErrorState
          title={copy.adminRequired}
          detail={copy.adminRequiredDetail}
        />
      </main>
    );
  return (
    <main className="page admin-page">
      <Outlet />
    </main>
  );
}
