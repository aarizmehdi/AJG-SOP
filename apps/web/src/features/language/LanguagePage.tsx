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
  const { language, setLanguage } = useLanguage();
  const [selected, setSelected] = useState(language);
  const navigate = useNavigate();
  return (
    <main className="centered-page">
      <section className="language-card">
        <span className="eyebrow">Your experience</span>
        <h1>Choose your language</h1>
        <p>
          The assistant will keep answering in this language until you change
          it.
        </p>
        <div className="language-grid">
          {choices.map((choice) => (
            <button
              key={choice.id}
              dir={choice.dir}
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
        <Button
          onClick={() => {
            setLanguage(selected);
            void navigate('/home');
          }}
        >
          Save and continue
        </Button>
      </section>
    </main>
  );
}
