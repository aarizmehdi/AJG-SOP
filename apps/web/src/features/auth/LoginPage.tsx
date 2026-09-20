import { ArrowRight } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { BrandMark } from '../../components/ui/BrandMark';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { useAuth0 } from '@auth0/auth0-react';
import { useLanguage } from '../language/useLanguage';

function LiveLoginButton() {
  const { loginWithRedirect, isLoading, error } = useAuth0();
  const { t } = useLanguage();
  return (
    <div
      className="login-actions"
      style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}
    >
      {error ? (
        <div
          role="alert"
          style={{
            padding: '12px',
            borderRadius: '8px',
            background: '#fef2f2',
            border: '1px solid #fca5a5',
            color: '#991b1b',
            fontSize: '14px',
            lineHeight: '1.4',
            textAlign: 'left',
          }}
        >
          <strong>Auth0 Login Error:</strong>
          <div style={{ marginTop: '4px', wordBreak: 'break-word' }}>
            {error.message}
          </div>
        </div>
      ) : null}
      <Button
        disabled={isLoading}
        onClick={() => {
          void loginWithRedirect();
        }}
      >
        {t('loginAction')} <ArrowRight size={18} aria-hidden="true" />
      </Button>
    </div>
  );
}

export default function LoginPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const appMode = import.meta.env.VITE_APP_MODE ?? 'fixture';
  const { isAuthenticated, isLoading } = useAuth0();

  if (appMode === 'live' && isLoading) {
    return <RouteSkeleton />;
  }

  if (appMode === 'live' && isAuthenticated) {
    return <Navigate to="/home" replace />;
  }

  const enterFixture = (
    identity: 'employee' | 'sop-admin' | 'system-admin',
  ) => {
    queryClient.clear();
    window.localStorage.setItem('ajt-fixture-identity', identity);
    void navigate('/home');
  };
  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="auth-brand-inner">
          <BrandMark />
          <div>
            <span className="eyebrow light">{t('loginEyebrow')}</span>
            <h1>{t('loginBrandTitle')}</h1>
            <p>{t('loginBrandDetail')}</p>
          </div>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <h2>{t('loginWelcome')}</h2>
          <p>{t('loginDetail')}</p>
          {(import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture' ? (
            <div className="login-actions">
              <Button
                onClick={() => {
                  enterFixture('employee');
                }}
              >
                {t('loginEmployee')} <ArrowRight size={18} aria-hidden="true" />
              </Button>
              <button
                className="login-secondary-action"
                onClick={() => {
                  enterFixture('sop-admin');
                }}
              >
                {t('loginAdmin')}
              </button>
              <button
                className="login-secondary-action"
                onClick={() => {
                  enterFixture('system-admin');
                }}
              >
                {t('loginSystemAdmin')}
              </button>
            </div>
          ) : (
            <LiveLoginButton />
          )}
        </div>
      </section>
    </main>
  );
}
