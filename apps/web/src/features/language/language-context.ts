import { createContext } from 'react';

export type Language = 'english' | 'urdu' | 'roman_urdu';
export type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
};

export const LanguageContext = createContext<LanguageContextValue | null>(null);
