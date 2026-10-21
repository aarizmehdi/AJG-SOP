import {
  BookOpen,
  Building2,
  ChevronDown,
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
import { useMemo, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import type { Profile } from '../../types/profile';

type AdminGroup = {
  id: string;
  label: string;
  links: { to: string; label: string; icon: typeof BookOpen }[];
};

function groupsFor(profile: Profile | undefined): AdminGroup[] {
  const systemAdmin =
    profile?.application_roles.includes('system_admin') ?? false;
  const sopAdmin = profile?.application_roles.includes('sop_admin') ?? false;
  if (!systemAdmin && !sopAdmin) return [];
  const knowledge = {
    id: 'knowledge',
    label: 'Knowledge',
    links: [
      { to: '/admin/policies', label: 'SOP Library', icon: BookOpen },
      { to: '/admin/review-queue', label: 'Review Queue', icon: ClipboardList },
      ...(systemAdmin
        ? [{ to: '/admin/add', label: 'Add SOP', icon: FilePlus2 }]
        : []),
    ],
  };
  if (!systemAdmin) return [knowledge];
  return [
    {
      id: 'overview',
      label: 'Overview',
      links: [
        { to: '/admin/overview', label: 'Overview', icon: LayoutDashboard },
      ],
    },
    knowledge,
    {
      id: 'people',
      label: 'People & Access',
      links: [
        { to: '/admin/users', label: 'Users', icon: Users },
        { to: '/admin/departments', label: 'Departments', icon: Building2 },
        { to: '/admin/locations', label: 'Locations', icon: MapPin },
        {
          to: '/admin/organizational-roles',
          label: 'Organizational Roles',
          icon: Tags,
        },
        { to: '/admin/access', label: 'Access', icon: SearchCheck },
      ],
    },
    {
      id: 'governance',
      label: 'Governance',
      links: [{ to: '/admin/audit', label: 'Audit Log', icon: ShieldCheck }],
    },
    {
      id: 'organization',
      label: 'Organization',
      links: [
        { to: '/admin/organization', label: 'Organization', icon: Settings },
      ],
    },
  ];
}

function linkIsActive(pathname: string, to: string) {
  if (pathname === to) return true;
  if (to === '/admin/policies') return pathname.startsWith('/admin/policies/');
  if (to === '/admin/review-queue')
    return pathname.startsWith('/admin/review/');
  return to === '/admin/users' && pathname.startsWith('/admin/users/');
}

export function AdminSidebarNavigation({
  profile,
  onNavigate,
}: {
  profile: Profile | undefined;
  onNavigate?: () => void;
}) {
  const location = useLocation();
  const groups = useMemo(() => groupsFor(profile), [profile]);
  const activeGroup =
    groups.find((group) =>
      group.links.some((link) => linkIsActive(location.pathname, link.to)),
    )?.id ?? groups[0]?.id;
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  return (
    <nav className="admin-sidebar-nav" aria-label="Administration">
      {groups.map((group) => {
        const open = group.id === activeGroup || expanded.has(group.id);
        return (
          <section className="admin-sidebar-group" key={group.id}>
            <button
              type="button"
              className="admin-sidebar-group-toggle"
              aria-expanded={open}
              aria-controls={`admin-nav-${group.id}`}
              onClick={() => {
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(group.id)) next.delete(group.id);
                  else next.add(group.id);
                  return next;
                });
              }}
            >
              <span>{group.label}</span>
              <ChevronDown aria-hidden="true" />
            </button>
            {open && (
              <div id={`admin-nav-${group.id}`} className="admin-sidebar-links">
                {group.links.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={
                      linkIsActive(location.pathname, to)
                        ? 'admin-sidebar-link active'
                        : 'admin-sidebar-link'
                    }
                    onClick={onNavigate}
                  >
                    <Icon size={17} aria-hidden="true" />
                    <span>{label}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </nav>
  );
}
