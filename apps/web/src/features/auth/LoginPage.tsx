import { ArrowRight, LockKeyhole } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { useAuth0 } from '@auth0/auth0-react';

function LiveLoginButton() {
  const { loginWithRedirect, isLoading } = useAuth0();
  return (
    <Button
      disabled={isLoading}
      onClick={() => {
        void loginWithRedirect();
      }}
    >
      Continue with Auth0 <ArrowRight size={18} />
    </Button>
  );
}

export default function LoginPage() {
  return (
    <main className="auth-page">
      <section className="auth-brand">
        <img src="/brand/aziz-jan-trust-logo.png" alt="Aziz Jan Trust" />
        <div>
          <span className="eyebrow light">SOP knowledge system</span>
          <h1>Policy guidance you can trust.</h1>
          <p>
            Find the organizational rule you need, with a clear source every
            time.
          </p>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <span className="icon-tile">
            <LockKeyhole />
          </span>
          <span className="eyebrow">Secure access</span>
          <h2>Welcome back</h2>
          <p>Sign in with your Aziz Jan Trust account.</p>
          {(import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture' ? (
            <>
              <Link
                className="button button--primary"
                to="/home"
                onClick={() => {
                  window.localStorage.setItem(
                    'ajt-fixture-identity',
                    'employee',
                  );
                }}
              >
                Use employee fixture <ArrowRight size={18} />
              </Link>
              <Link
                className="fixture-link"
                to="/admin"
                onClick={() => {
                  window.localStorage.setItem(
                    'ajt-fixture-identity',
                    'sop-admin',
                  );
                }}
              >
                Use administrator fixture
              </Link>
              <small>
                Fixture identities are available only while APP_MODE=fixture.
              </small>
            </>
          ) : (
            <LiveLoginButton />
          )}
        </div>
      </section>
    </main>
  );
}
