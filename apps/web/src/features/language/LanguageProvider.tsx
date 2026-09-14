import { useEffect, useState, type PropsWithChildren } from 'react';
import { LanguageContext, type Language } from './language-context';

const supported = new Set<Language>(['english', 'urdu', 'roman_urdu']);

export function LanguageProvider({ children }: PropsWithChildren) {
  const [language, setLanguageState] = useState<Language>(() => {
    const stored = localStorage.getItem('ajt-language') as Language | null;
    return stored && supported.has(stored) ? stored : 'english';
  });
  useEffect(() => {
    document.documentElement.dir = language === 'urdu' ? 'rtl' : 'ltr';
    document.documentElement.lang = language === 'urdu' ? 'ur' : 'en';
    localStorage.setItem('ajt-language', language);
  }, [language]);
  return (
    <LanguageContext value={{ language, setLanguage: setLanguageState }}>
      {children}
    </LanguageContext>
  );
}
