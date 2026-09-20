import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type PropsWithChildren } from 'react';
import { configureAccessTokenProvider } from '../api/client';
import { LanguageProvider } from '../features/language/LanguageProvider';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function Auth0Bridge({ children }: PropsWithChildren) {
  const { getAccessTokenSilently } = useAuth0();
  useEffect(() => {
    configureAccessTokenProvider(async () => getAccessTokenSilently());
    return () => {
      configureAccessTokenProvider(() => Promise.resolve(null));
    };
  }, [getAccessTokenSilently]);
  return children;
}

function IdentityProvider({ children }: PropsWithChildren) {
  if ((import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture')
    return children;
  const domain = import.meta.env.VITE_AUTH0_DOMAIN;
  const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID;
  const audience = import.meta.env.VITE_AUTH0_AUDIENCE;
  if (!domain || !clientId || !audience)
    throw new Error('Auth0 web configuration is incomplete');

  const onRedirectCallback = (appState?: { returnTo?: string }) => {
    if (window.location.search.includes('code=')) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    const target =
      appState?.returnTo && appState.returnTo !== '/login'
        ? appState.returnTo
        : '/home';
    if (window.location.pathname !== target) {
      window.location.href = target;
    }
  };

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{ redirect_uri: window.location.origin, audience }}
      onRedirectCallback={onRedirectCallback}
      cacheLocation="memory"
      useRefreshTokens
    >
      <Auth0Bridge>{children}</Auth0Bridge>
    </Auth0Provider>
  );
}

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <IdentityProvider>
      <LanguageProvider>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </LanguageProvider>
    </IdentityProvider>
  );
}
