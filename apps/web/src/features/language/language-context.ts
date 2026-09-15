import { createContext } from 'react';
import type { Profile } from '../../types/profile';
import type { MessageKey } from './messages';

export type Language = 'english' | 'urdu' | 'roman_urdu';
export type LanguageContextValue = {
  language: Language;
  hasPreference: boolean;
  profileId: string | null;
  bindProfile: (profile: Profile) => void;
  setLanguage: (language: Language) => Promise<void>;
  t: (key: MessageKey) => string;
};

export const LanguageContext = createContext<LanguageContextValue | null>(null);
