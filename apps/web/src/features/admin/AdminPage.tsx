import { FilePlus2, Files, ShieldCheck } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { profileSchema } from '../../types/profile';

export default function AdminPage() {
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  if (profile.isPending) return <RouteSkeleton />;
  if (
    profile.isError ||
    !profile.data.application_roles.some(
      (role) => role === 'sop_admin' || role === 'system_admin',
    )
  )
    return (
      <main className="page">
        <ErrorState
          title="Administrative access required"
          detail="Your account is not assigned to SOP administration."
        />
      </main>
    );
  return (
    <main className="page admin-page">
      <div className="admin-heading">
        <div>
          <span className="eyebrow">SOP administration</span>
          <h1>Policy Library</h1>
        </div>
        <span className="admin-badge">
          <ShieldCheck size={15} />
          Scoped administrator
        </span>
      </div>
      <nav className="tabs" aria-label="Policy administration">
        <NavLink end to="/admin">
          <Files size={17} />
          Library
        </NavLink>
        <NavLink to="/admin/add">
          <FilePlus2 size={17} />
          Add SOP
        </NavLink>
      </nav>
      <Outlet />
    </main>
  );
}
