import { useAuth0 } from '@auth0/auth0-react';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Languages, LogOut } from 'lucide-react';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Profile } from '../../types/profile';
import { useLanguage } from '../../features/language/useLanguage';

function LiveLogout({
  close,
  itemRef,
}: {
  close: () => void;
  itemRef: React.Ref<HTMLButtonElement>;
}) {
  const { logout } = useAuth0();
  const { t } = useLanguage();
  return (
    <button
      ref={itemRef}
      role="menuitem"
      onClick={() => {
        close();
        void logout({
          logoutParams: { returnTo: `${window.location.origin}/login` },
        });
      }}
    >
      <LogOut size={17} aria-hidden="true" /> {t('logout')}
    </button>
  );
}

export function ProfileMenu({ profile }: { profile: Profile | undefined }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const languageItem = useRef<HTMLAnchorElement>(null);
  const logoutItem = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, language } = useLanguage();
  const isFixture = (import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture';
  const roles = profile?.application_roles ?? [];
  const role = roles.includes('system_admin')
    ? t('roleSystemAdmin')
    : roles.includes('sop_admin')
      ? t('roleSopAdmin')
      : t('roleEmployee');

  useEffect(() => {
    if (!open) return;
    languageItem.current?.focus();
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target))
        setOpen(false);
    };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  const moveFocus = (event: KeyboardEvent<HTMLElement>) => {
    const items = [languageItem.current, logoutItem.current].filter(
      (item): item is HTMLAnchorElement | HTMLButtonElement => item !== null,
    );
    const current = items.indexOf(document.activeElement as HTMLAnchorElement);
    let next: number;
    if (event.key === 'ArrowDown') next = (current + 1) % items.length;
    else if (event.key === 'ArrowUp')
      next = (current - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    else return;
    event.preventDefault();
    items[next]?.focus();
  };

  const fixtureLogout = () => {
    window.localStorage.removeItem('ajt-fixture-identity');
    queryClient.clear();
    setOpen(false);
    void navigate('/login', { replace: true });
  };

  const initials =
    profile?.display_name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .slice(0, 2) ?? 'AJ';

  return (
    <div className="profile-root" ref={root}>
      <button
        className="avatar"
        ref={trigger}
        aria-label={t('profile')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{initials}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          className="profile-menu"
          role="menu"
          aria-label={t('profile')}
          onKeyDown={moveFocus}
        >
          <div className="profile-summary">
            <strong>{profile?.display_name ?? t('brandName')}</strong>
            {profile?.email && <span dir="auto">{profile.email}</span>}
            <small>{role}</small>
          </div>
          <Link
            ref={languageItem}
            role="menuitem"
            to="/language"
            onClick={() => {
              setOpen(false);
            }}
          >
            <Languages size={17} aria-hidden="true" />
            <span>{t('language')}</span>
            <small>
              {language === 'roman_urdu'
                ? 'Roman Urdu'
                : language === 'urdu'
                  ? 'اردو'
                  : 'English'}
            </small>
          </Link>
          {isFixture ? (
            <button ref={logoutItem} role="menuitem" onClick={fixtureLogout}>
              <LogOut size={17} aria-hidden="true" /> {t('logout')}
            </button>
          ) : (
            <LiveLogout
              itemRef={logoutItem}
              close={() => {
                setOpen(false);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
