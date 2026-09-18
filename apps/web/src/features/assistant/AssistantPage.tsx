import { useMutation } from '@tanstack/react-query';
import { ArrowUp, BookOpenText, Mic, Square, X } from 'lucide-react';
import {
  useEffect,
  useCallback,
  useRef,
  useState,
  type SyntheticEvent,
  type KeyboardEvent,
} from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { BrandMark } from '../../components/ui/BrandMark';
import {
  verifiedAnswerSchema,
  type VerifiedAnswer,
} from '../../types/assistant';
import { useLanguage } from '../language/useLanguage';
import { useVoiceInput } from './useVoiceInput';

type Turn = {
  id: string;
  question: string;
  result?: VerifiedAnswer;
  failed?: boolean;
};
type Request = {
  id: string;
  question: string;
  responseLanguage: 'english' | 'urdu' | 'roman_urdu';
};

export default function AssistantPage() {
  const [question, setQuestion] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const { language, t } = useLanguage();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const inFlight = useRef(false);
  const followBottom = useRef(true);
  const voiceEnabled = import.meta.env.VITE_VOICE_INPUT_ENABLED === 'true';
  const acceptTranscript = useCallback((transcript: string) => {
    setQuestion(transcript);
    window.requestAnimationFrame(() => {
      const field = textarea.current;
      if (!field) return;
      field.style.height = 'auto';
      field.style.height = `${Math.min(field.scrollHeight, 144).toString()}px`;
      field.style.overflowY = field.scrollHeight > 144 ? 'auto' : 'hidden';
      field.focus();
    });
  }, []);
  const voice = useVoiceInput({
    enabled: voiceEnabled,
    language,
    onTranscript: acceptTranscript,
  });
  const answer = useMutation({
    mutationFn: async (request: Request) => {
      const result = await apiRequest(
        '/assistant/answer',
        verifiedAnswerSchema,
        {
          method: 'POST',
          body: JSON.stringify({
            question: request.question,
            language: request.responseLanguage,
            session_id: sessionId,
          }),
        },
      );
      if (result.language !== request.responseLanguage)
        throw new Error('Assistant response language did not match preference');
      return result;
    },
    onSuccess: (result, request) => {
      setSessionId(result.session_id);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === request.id ? { ...turn, result } : turn,
        ),
      );
      textarea.current?.focus();
    },
    onError: (_error, request) => {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === request.id ? { ...turn, failed: true } : turn,
        ),
      );
    },
    onSettled: () => {
      inFlight.current = false;
    },
  });

  useEffect(() => {
    textarea.current?.focus();
  }, []);
  useEffect(() => {
    const updateFollow = () => {
      followBottom.current =
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 260;
    };
    window.addEventListener('scroll', updateFollow, { passive: true });
    return () => {
      window.removeEventListener('scroll', updateFollow);
    };
  }, []);
  useEffect(() => {
    if (!followBottom.current || !turns.length) return;
    const frame = window.requestAnimationFrame(() => {
      bottom.current?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
        block: 'end',
      });
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [turns, answer.isPending]);

  const resizeComposer = () => {
    const field = textarea.current;
    if (!field) return;
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 144).toString()}px`;
    field.style.overflowY = field.scrollHeight > 144 ? 'auto' : 'hidden';
  };
  const send = () => {
    const trimmed = question.trim();
    if (!trimmed || inFlight.current || answer.isPending || composing.current)
      return;
    inFlight.current = true;
    followBottom.current = true;
    const id = crypto.randomUUID();
    setTurns((current) => [...current, { id, question: trimmed }]);
    setQuestion('');
    if (textarea.current) {
      textarea.current.style.height = 'auto';
      textarea.current.style.overflowY = 'hidden';
    }
    answer.mutate({ id, question: trimmed, responseLanguage: language });
  };
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    send();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== 'Enter' ||
      event.shiftKey ||
      event.nativeEvent.isComposing ||
      composing.current
    )
      return;
    event.preventDefault();
    send();
  };
  return (
    <main className="page assistant-page">
      <header className="assistant-heading">
        <div>
          <span className="eyebrow">{t('assistantEyebrow')}</span>
          <h1>{t('assistantTitle')}</h1>
          <p>{t('assistantLead')}</p>
        </div>
      </header>
      <section className="conversation" aria-live="polite">
        {!turns.length && (
          <div className="assistant-welcome">
            <BrandMark />
            <h2>{t('assistantWelcome')}</h2>
            <p>{t('assistantWelcomeDetail')}</p>
          </div>
        )}
        {turns.map((turn) => (
          <div className="turn" key={turn.id}>
            <div className="user-message" dir="auto">
              {turn.question}
            </div>
            {turn.result && (
              <div className="assistant-message">
                <BrandMark compact />
                <div>
                  <span className="answer-label">{t('assistantAnswer')}</span>
                  <p dir={language === 'urdu' ? 'rtl' : 'ltr'}>
                    {turn.result.answer}
                  </p>
                  {turn.result.citations.length > 0 && (
                    <div className="answer-sources">
                      <strong>{t('assistantSources')}</strong>
                      {turn.result.citations.map((citation) => (
                        <Link
                          key={citation.chunk_id}
                          to={`/policies/${citation.policy_id}?section=${citation.section_id}`}
                        >
                          <BookOpenText aria-hidden="true" />
                          <span>
                            <b dir="auto">{citation.policy_title}</b>
                            <small dir="auto">
                              {citation.heading_path.join(' → ')}
                              {citation.source.page_start
                                ? ` · ${t('assistantSourcePage')} ${String(citation.source.page_start)}`
                                : ''}
                            </small>
                          </span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
            {turn.failed && (
              <div className="assistant-failure" role="alert">
                <strong>{t('assistantNoAnswer')}</strong>
                <p>{t('assistantErrorDetail')}</p>
              </div>
            )}
          </div>
        ))}
        {answer.isPending && (
          <div className="assistant-message pending" role="status">
            <BrandMark compact />
            <div>
              <span className="pending-bar" aria-hidden="true" />
              <small>{t('assistantPending')}</small>
            </div>
          </div>
        )}
        <div ref={bottom} />
      </section>
      <form className="composer surface" onSubmit={submit}>
        <textarea
          ref={textarea}
          aria-label={t('assistantInput')}
          dir="auto"
          rows={1}
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
            resizeComposer();
          }}
          onKeyDown={onKeyDown}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          placeholder={t('assistantPlaceholder')}
        />
        <div className="composer-actions">
          {voiceEnabled && voice.state !== 'listening' && (
            <button
              className="voice-button"
              type="button"
              aria-label={t('voiceStart')}
              disabled={voice.state === 'transcribing'}
              onClick={() => {
                void voice.start();
              }}
            >
              <Mic aria-hidden="true" />
            </button>
          )}
          {voiceEnabled && voice.state === 'listening' && (
            <>
              <button
                className="voice-button recording"
                type="button"
                aria-label={t('voiceStop')}
                onClick={voice.stop}
              >
                <Square aria-hidden="true" />
              </button>
              <button
                className="voice-button"
                type="button"
                aria-label={t('voiceCancel')}
                onClick={voice.cancel}
              >
                <X aria-hidden="true" />
              </button>
            </>
          )}
          <button
            className="send-button"
            type="submit"
            aria-label={t('assistantSend')}
            disabled={answer.isPending || !question.trim()}
          >
            <ArrowUp aria-hidden="true" />
          </button>
        </div>
        <small aria-live="polite">
          {voice.state === 'listening'
            ? t('voiceListening')
            : voice.state === 'transcribing'
              ? t('voiceTranscribing')
              : voice.state === 'error'
                ? t('voiceError')
                : t('assistantComposerNote')}
        </small>
      </form>
    </main>
  );
}
