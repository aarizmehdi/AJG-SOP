import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { FirebaseAuthProvider } from '../features/auth/FirebaseAuthProvider';
import { LanguageProvider } from '../features/language/LanguageProvider';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <FirebaseAuthProvider>
      <LanguageProvider>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </LanguageProvider>
    </FirebaseAuthProvider>
  );
}
