import { use } from 'react';
import { LanguageContext } from './language-context';

export function useLanguage() {
  const value = use(LanguageContext);
  if (!value) throw new Error('LanguageProvider is missing');
  return value;
}
