import {
  BookOpen,
  Building2,
  ClipboardList,
  FilePlus2,
  LayoutDashboard,
  MapPin,
  SearchCheck,
  Settings,
  ShieldCheck,
  Tags,
  Users,
} from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
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
  const isSystemAdmin = profile.data.application_roles.includes('system_admin');
  const knowledgeLinks = [
    { to: '/admin/policies', label: 'SOP Library', icon: BookOpen },
    { to: '/admin/review-queue', label: 'Review Queue', icon: ClipboardList },
    ...(isSystemAdmin
      ? [{ to: '/admin/add', label: 'Add SOP', icon: FilePlus2 }]
      : []),
  ];
  const systemLinks = [
    { to: '/admin/overview', label: 'Overview', icon: LayoutDashboard },
    { to: '/admin/users', label: 'Users', icon: Users },
    { to: '/admin/departments', label: 'Departments', icon: Building2 },
    { to: '/admin/locations', label: 'Locations', icon: MapPin },
    {
      to: '/admin/organizational-roles',
      label: 'Organizational Roles',
      icon: Tags,
    },
    { to: '/admin/access', label: 'Access', icon: SearchCheck },
    { to: '/admin/audit', label: 'Audit Log', icon: ShieldCheck },
    { to: '/admin/organization', label: 'Organization', icon: Settings },
  ];
  return (
    <main className="page admin-page">
      <header className="control-plane-header">
        <div>
          <span className="eyebrow">
            {isSystemAdmin ? 'System administration' : 'SOP administration'}
          </span>
          <h1>{isSystemAdmin ? 'AJG control plane' : 'Knowledge workspace'}</h1>
        </div>
        <span className="admin-context-badge">
          {isSystemAdmin
            ? 'Organization administrator'
            : 'Scoped SOP administrator'}
        </span>
      </header>
      <div className="control-plane-layout">
        <aside className="control-plane-nav">
          {isSystemAdmin && (
            <NavGroup label="System" links={systemLinks.slice(0, 1)} />
          )}
          <NavGroup label="Knowledge" links={knowledgeLinks} />
          {isSystemAdmin && (
            <>
              <NavGroup
                label="People & access"
                links={systemLinks.slice(1, 5)}
              />
              <NavGroup label="Governance" links={systemLinks.slice(5, 7)} />
              <NavGroup label="Organization" links={systemLinks.slice(7)} />
            </>
          )}
        </aside>
        <div className="control-plane-content">
          <Outlet />
        </div>
      </div>
    </main>
  );
}

function NavGroup({
  label,
  links,
}: {
  label: string;
  links: { to: string; label: string; icon: typeof BookOpen }[];
}) {
  return (
    <div className="control-plane-nav-group">
      <span>{label}</span>
      {links.map(({ to, label: linkLabel, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `control-plane-nav-link${isActive ? ' active' : ''}`
          }
        >
          <Icon size={17} aria-hidden="true" />
          {linkLabel}
        </NavLink>
      ))}
    </div>
  );
}
