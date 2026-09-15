import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { useLanguage } from './useLanguage';

const choices = [
  {
    id: 'english',
    label: 'English',
    sample: 'Continue in English',
    dir: 'ltr',
  },
  { id: 'urdu', label: 'اردو', sample: 'اردو میں جاری رکھیں', dir: 'rtl' },
  {
    id: 'roman_urdu',
    label: 'Roman Urdu',
    sample: 'Roman Urdu mein jari rakhein',
    dir: 'ltr',
  },
] as const;

export default function LanguagePage() {
  const { language, setLanguage, t } = useLanguage();
  const [selected, setSelected] = useState(language);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const navigate = useNavigate();
  const save = async () => {
    if (saving) return;
    setSaving(true);
    setError(false);
    try {
      await setLanguage(selected);
      void navigate('/home', { replace: true });
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };
  return (
    <main className="centered-page">
      <section className="language-card">
        <span className="eyebrow">{t('languageEyebrow')}</span>
        <h1>{t('languageTitle')}</h1>
        <p>{t('languageDetail')}</p>
        <div
          className="language-grid"
          role="group"
          aria-label={t('languageTitle')}
        >
          {choices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              dir={choice.dir}
              aria-pressed={selected === choice.id}
              className={`language-option${selected === choice.id ? ' selected' : ''}`}
              onClick={() => {
                setSelected(choice.id);
              }}
            >
              <strong>{choice.label}</strong>
              <span>{choice.sample}</span>
            </button>
          ))}
        </div>
        {error && (
          <p className="language-error" role="alert">
            {t('languageError')}
          </p>
        )}
        <Button
          disabled={saving}
          onClick={() => {
            void save();
          }}
        >
          {saving ? t('languageSaving') : t('languageSave')}
        </Button>
      </section>
    </main>
  );
}
