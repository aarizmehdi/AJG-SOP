import { ArrowUp, BookOpenText, Mic, Square, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  useEffect,
  useCallback,
  useRef,
  useState,
  type SyntheticEvent,
  type KeyboardEvent,
} from 'react';
import { Link } from 'react-router-dom';
import { BrandMark } from '../../components/ui/BrandMark';
import { type StreamAnswer } from '../../types/assistant';
import { useLanguage } from '../language/useLanguage';
import { streamAssistant } from './streamAssistant';
import { useVoiceInput } from './useVoiceInput';

type Turn = {
  id: string;
  question: string;
  result?: StreamAnswer;
  streaming?: string | undefined;
  stage?:
    | 'retrieving'
    | 'reading'
    | 'generating'
    | 'repairing'
    | 'verifying'
    | undefined;
  failed?: boolean;
};
const stageKeys = {
  retrieving: 'assistantStageRetrieving',
  reading: 'assistantStageReading',
  generating: 'assistantStageGenerating',
  repairing: 'assistantStageRepairing',
  verifying: 'assistantStageVerifying',
} as const;

export default function AssistantPage() {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const { language, t } = useLanguage();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const inFlight = useRef(false);
  const abort = useRef<AbortController | null>(null);
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
  useEffect(() => () => abort.current?.abort(), []);

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
  }, [turns, pending]);

  const resizeComposer = () => {
    const field = textarea.current;
    if (!field) return;
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 144).toString()}px`;
    field.style.overflowY = field.scrollHeight > 144 ? 'auto' : 'hidden';
  };
  const send = () => {
    const trimmed = question.trim();
    if (!trimmed || inFlight.current || composing.current) return;
    inFlight.current = true;
    followBottom.current = true;
    const id = crypto.randomUUID();
    const history = turns
      .filter((turn) => turn.result)
      .slice(-8)
      .map((turn) => ({
        role: 'user' as const,
        content: turn.question.slice(0, 1000),
      }));
    setTurns((current) => [...current, { id, question: trimmed }]);
    setPending(true);
    setQuestion('');
    if (textarea.current) {
      textarea.current.style.height = 'auto';
      textarea.current.style.overflowY = 'hidden';
    }
    const controller = new AbortController();
    abort.current = controller;
    void streamAssistant(trimmed, language, history, controller.signal, {
      onStatus: (stage) => {
        setTurns((current) =>
          current.map((turn) => (turn.id === id ? { ...turn, stage } : turn)),
        );
      },
      onDelta: (text) => {
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id
              ? { ...turn, streaming: (turn.streaming ?? '') + text }
              : turn,
          ),
        );
      },
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id
              ? { ...turn, result, streaming: undefined, stage: undefined }
              : turn,
          ),
        );
        textarea.current?.focus();
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id
              ? {
                  ...turn,
                  failed: true,
                  streaming: undefined,
                  stage: undefined,
                }
              : turn,
          ),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          inFlight.current = false;
          setPending(false);
        }
      });
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
  const latestStage = turns.at(-1)?.stage;
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
                  <div
                    className="answer-markdown"
                    dir={language === 'urdu' ? 'rtl' : 'ltr'}
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      skipHtml
                      components={{
                        a: ({ children }) => <span>{children}</span>,
                        img: () => null,
                      }}
                    >
                      {turn.result.answer}
                    </ReactMarkdown>
                  </div>
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
            {turn.streaming !== undefined && (
              <div className="assistant-message" aria-live="polite">
                <BrandMark compact />
                <div
                  className="answer-markdown"
                  dir={language === 'urdu' ? 'rtl' : 'ltr'}
                >
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    skipHtml
                    components={{
                      a: ({ children }) => <span>{children}</span>,
                      img: () => null,
                    }}
                  >
                    {turn.streaming}
                  </ReactMarkdown>
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
        {pending && !turns.at(-1)?.streaming && (
          <div className="assistant-message pending" role="status">
            <BrandMark compact />
            <div>
              <span className="pending-bar" aria-hidden="true" />
              <small>
                {latestStage
                  ? t(stageKeys[latestStage])
                  : t('assistantPending')}
              </small>
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
          maxLength={1000}
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
            disabled={pending || !question.trim()}
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
