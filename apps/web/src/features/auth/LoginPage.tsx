import { ArrowRight } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { BrandMark } from '../../components/ui/BrandMark';
import { useAuth0 } from '@auth0/auth0-react';
import { useLanguage } from '../language/useLanguage';

function LiveLoginButton() {
  const { loginWithRedirect, isLoading } = useAuth0();
  const { t } = useLanguage();
  return (
    <Button
      disabled={isLoading}
      onClick={() => {
        void loginWithRedirect();
      }}
    >
      {t('loginAction')} <ArrowRight size={18} aria-hidden="true" />
    </Button>
  );
}

export default function LoginPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
