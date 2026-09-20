import { createContext, use } from 'react';

export type FirebaseAuthState = {
  initialized: boolean;
  authenticated: boolean;
  initializationError: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

export const FirebaseAuthContext = createContext<FirebaseAuthState | null>(
  null,
);

export function useFirebaseAuth() {
  const value = use(FirebaseAuthContext);
  if (!value) throw new Error('FirebaseAuthProvider is missing');
  return value;
}
