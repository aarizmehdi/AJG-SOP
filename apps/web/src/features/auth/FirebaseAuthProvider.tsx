import {
  browserLocalPersistence,
  getAuth,
  onIdTokenChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type Auth,
} from 'firebase/auth';
import {
  getApp,
  getApps,
  initializeApp,
  type FirebaseError,
} from 'firebase/app';
import { useEffect, useMemo, useState, type PropsWithChildren } from 'react';
import { configureAccessTokenProvider } from '../../api/client';
import { FirebaseAuthContext } from './firebase-auth-context';

const isFixture = (import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture';

function buildAuth(): Auth | null {
  if (isFixture) return null;
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
  const authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN;
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID;
  const appId = import.meta.env.VITE_FIREBASE_APP_ID;
  if (!apiKey || !authDomain || !projectId || !appId) {
    throw new Error('Firebase web configuration is incomplete');
  }
  const config = { apiKey, authDomain, projectId, appId };
  const app = getApps().length ? getApp() : initializeApp(config);
  return getAuth(app);
}

function errorMessage(error: unknown): string {
  const code = (error as FirebaseError | undefined)?.code;
  if (
    code === 'auth/invalid-credential' ||
    code === 'auth/user-not-found' ||
    code === 'auth/wrong-password' ||
    code === 'auth/invalid-email'
  ) {
    return 'invalidCredentials';
  }
  if (code === 'auth/too-many-requests') return 'tooManyAttempts';
  if (code === 'auth/network-request-failed') return 'authNetworkError';
  return 'signInFailed';
}

export function FirebaseAuthProvider({ children }: PropsWithChildren) {
  const [bootstrap] = useState<{ auth: Auth | null; error: string | null }>(
    () => {
      try {
        return { auth: buildAuth(), error: null };
      } catch {
        return { auth: null, error: 'authInitializationFailed' };
      }
    },
  );
  const auth = bootstrap.auth;
  const [initialized, setInitialized] = useState(
    isFixture || bootstrap.error !== null,
  );
  const [authenticated, setAuthenticated] = useState(false);
  const [initializationError, setInitializationError] = useState<string | null>(
    bootstrap.error,
  );

  useEffect(() => {
    if (!auth) {
      configureAccessTokenProvider(() => Promise.resolve(null));
      return;
    }
    configureAccessTokenProvider(
      async () => auth.currentUser?.getIdToken() ?? null,
    );
    let unsubscribe = () => {};
    void setPersistence(auth, browserLocalPersistence)
      .then(() => {
        unsubscribe = onIdTokenChanged(
          auth,
          (user) => {
            setAuthenticated(Boolean(user));
            setInitializationError(null);
            setInitialized(true);
          },
          () => {
            setInitializationError('authInitializationFailed');
            setInitialized(true);
          },
        );
      })
      .catch(() => {
        setInitializationError('authInitializationFailed');
        setInitialized(true);
      });
    return () => {
      unsubscribe();
      configureAccessTokenProvider(() => Promise.resolve(null));
    };
  }, [auth]);

  const value = useMemo(
    () => ({
      initialized,
      authenticated,
      initializationError,
      signIn: async (email: string, password: string) => {
        if (!auth) throw new Error('signInUnavailable');
        try {
          await signInWithEmailAndPassword(auth, email, password);
          setAuthenticated(true);
        } catch (error) {
          throw new Error(errorMessage(error), { cause: error });
        }
      },
      signOut: async () => {
        if (auth) await firebaseSignOut(auth);
        setAuthenticated(false);
        window.localStorage.removeItem('ajt-active-language-profile');
      },
    }),
    [auth, authenticated, initialized, initializationError],
  );

  return <FirebaseAuthContext value={value}>{children}</FirebaseAuthContext>;
}
