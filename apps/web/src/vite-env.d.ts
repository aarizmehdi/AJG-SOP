/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_MODE?: 'fixture' | 'live';
  readonly VITE_API_URL?: string;
  readonly VITE_AUTH0_DOMAIN?: string;
  readonly VITE_AUTH0_CLIENT_ID?: string;
  readonly VITE_AUTH0_AUDIENCE?: string;
  readonly VITE_VOICE_INPUT_ENABLED?: 'true' | 'false';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
