import {
  useCallback,
  useLayoutEffect,
  useState,
  type PropsWithChildren,
} from 'react';
import { z } from 'zod';
import { apiRequest } from '../../api/client';
import type { Profile } from '../../types/profile';
import { LanguageContext, type Language } from './language-context';
import { messages, type MessageKey } from './messages';

const supported = new Set<Language>(['english', 'urdu', 'roman_urdu']);
const responseSchema = z.object({
  preferred_language: z.enum(['english', 'urdu', 'roman_urdu']),
});
const isLanguage = (value: string | null): value is Language =>
  value !== null && supported.has(value as Language);
const preferenceKey = (profile: Profile) =>
  `ajt-language:${profile.organization_id}:${profile.id}`;
const activeProfileKey = 'ajt-active-language-profile';
const bootstrapLanguage = (): Language => {
  const key = window.localStorage.getItem(activeProfileKey);
  const saved = key ? window.localStorage.getItem(key) : null;
  return isLanguage(saved) ? saved : 'english';
};

export function LanguageProvider({ children }: PropsWithChildren) {
  const [language, setLanguageState] = useState<Language>(bootstrapLanguage);
  const [hasPreference, setHasPreference] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [storageKey, setStorageKey] = useState<string | null>(null);

  const bindProfile = useCallback(
    (profile: Profile) => {
      const key = preferenceKey(profile);
      if (key === storageKey) return;
      const local = window.localStorage.getItem(key);
      // Fixture profiles carry an artificial English default, not an employee choice.
      const remote =
        (import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture'
          ? null
          : profile.preferred_language;
      const selected = isLanguage(local)
        ? local
        : isLanguage(remote)
          ? remote
          : null;
      setLanguageState(selected ?? 'english');
      setHasPreference(selected !== null);
      setProfileId(profile.id);
      setStorageKey(key);
      window.localStorage.setItem(activeProfileKey, key);
    },
    [storageKey],
  );

  const setLanguage = useCallback(
    async (selected: Language) => {
      if (!storageKey)
        throw new Error('A profile must be loaded before setting language');
      await apiRequest(
        `/profile/language?language=${encodeURIComponent(selected)}`,
        responseSchema,
        { method: 'PUT' },
      );
      window.localStorage.setItem(storageKey, selected);
      setLanguageState(selected);
      setHasPreference(true);
    },
    [storageKey],
  );

  const t = useCallback(
    (key: MessageKey) => messages[language][key],
    [language],
  );

  useLayoutEffect(() => {
    document.documentElement.dir = language === 'urdu' ? 'rtl' : 'ltr';
    document.documentElement.lang =
      language === 'urdu' ? 'ur' : language === 'roman_urdu' ? 'ur-Latn' : 'en';
    document.documentElement.dataset.locale = language;
  }, [language]);
  return (
    <LanguageContext
      value={{
        language,
        hasPreference,
        profileId,
        bindProfile,
        setLanguage,
        t,
      }}
    >
      {children}
    </LanguageContext>
  );
}
