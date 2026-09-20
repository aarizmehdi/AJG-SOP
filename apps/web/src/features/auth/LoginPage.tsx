import { ArrowRight } from 'lucide-react';
import { useState, type SyntheticEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { BrandMark } from '../../components/ui/BrandMark';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { useLanguage } from '../language/useLanguage';
import { useFirebaseAuth } from './firebase-auth-context';

function LiveLoginForm() {
  const { signIn } = useFirebaseAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      void navigate('/home', { replace: true });
    } catch (caught) {
      const key = caught instanceof Error ? caught.message : 'signInFailed';
      setError(
        key === 'invalidCredentials'
          ? t('invalidCredentials')
          : key === 'tooManyAttempts'
            ? t('tooManyAttempts')
            : key === 'authNetworkError'
              ? t('authNetworkError')
              : t('signInFailed'),
      );
    } finally {
      setPending(false);
    }
  };
  return (
    <form
      className="login-form"
      onSubmit={(event) => {
        void submit(event);
      }}
    >
      <label htmlFor="login-email">{t('emailAddress')}</label>
      <input
        id="login-email"
        type="email"
        value={email}
        onChange={(event) => {
          setEmail(event.target.value);
        }}
        autoComplete="username"
        required
        disabled={pending}
      />
      <label htmlFor="login-password">{t('password')}</label>
      <input
        id="login-password"
        type="password"
        value={password}
        onChange={(event) => {
          setPassword(event.target.value);
        }}
        autoComplete="current-password"
        required
        disabled={pending}
      />
      {error ? (
        <div className="login-error" role="alert">
          {error}
        </div>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? t('signingIn') : t('loginAction')}{' '}
        {!pending && <ArrowRight size={18} aria-hidden="true" />}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const appMode = import.meta.env.VITE_APP_MODE ?? 'fixture';
  const { authenticated, initialized, initializationError } = useFirebaseAuth();

  if (appMode === 'live' && !initialized) {
    return <RouteSkeleton />;
  }

  if (appMode === 'live' && authenticated) {
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
          ) : initializationError ? (
            <div className="login-error" role="alert">
              {t('authInitializationFailed')}
            </div>
          ) : (
            <LiveLoginForm />
          )}
        </div>
      </section>
    </main>
  );
}
