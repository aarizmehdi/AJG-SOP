import { useMutation } from '@tanstack/react-query';
import { ArrowUp, BookOpenText, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import {
  verifiedAnswerSchema,
  type VerifiedAnswer,
} from '../../types/assistant';
import { useLanguage } from '../language/useLanguage';

type Turn = { question: string; result: VerifiedAnswer };

export default function AssistantPage() {
  const [question, setQuestion] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const { language } = useLanguage();
  const answer = useMutation({
    mutationFn: (value: string) =>
      apiRequest('/assistant/answer', verifiedAnswerSchema, {
        method: 'POST',
        body: JSON.stringify({
          question: value,
          language,
          session_id: sessionId,
        }),
      }),
    onSuccess: (result, asked) => {
      setSessionId(result.session_id);
      setTurns((current) => [...current, { question: asked, result }]);
      setQuestion('');
    },
  });
  const submit = (event: React.SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (question.trim().length > 1) answer.mutate(question.trim());
  };
  return (
    <main
      className={`page assistant-page${language === 'urdu' ? ' urdu' : ''}`}
    >
      <header className="assistant-heading">
        <div>
          <span className="eyebrow">Grounded guidance</span>
          <h1>SOP Assistant</h1>
          <p>Ask a question and inspect the verified source.</p>
        </div>
        <span className="verified-label">
          <ShieldCheck />
          Verified before display
        </span>
      </header>
      <section className="conversation" aria-live="polite">
        {!turns.length && (
          <div className="assistant-welcome">
            <span className="assistant-mark">AJ</span>
            <h2>How can I help with an SOP?</h2>
            <p>
              I will answer only from published policy sections available to
              you.
            </p>
          </div>
        )}
        {turns.map((turn) => (
          <div
            className="turn"
            key={`${turn.result.session_id}-${turn.question}`}
          >
            <div className="user-message">{turn.question}</div>
            <div className="assistant-message">
              <span className="assistant-mark">AJ</span>
              <div>
                <span className="answer-label">Answer</span>
                <p>{turn.result.answer}</p>
                {turn.result.citations.length > 0 && (
                  <div className="answer-sources">
                    <strong>Sources</strong>
                    {turn.result.citations.map((citation) => (
                      <Link
                        key={citation.chunk_id}
                        to={`/policies/${citation.policy_id}?section=${citation.section_id}`}
                      >
                        <BookOpenText />
                        <span>
                          <b>{citation.policy_title}</b>
                          <small>
                            {citation.heading_path.join(' → ')}
                            {citation.source.page_start
                              ? ` · Page ${String(citation.source.page_start)}`
                              : ''}
                          </small>
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {answer.isPending && (
          <div className="assistant-message pending">
            <span className="assistant-mark">AJ</span>
            <div>
              <div className="thinking-line">
                <span />
                <span />
                <span />
              </div>
              <small>
                Retrieving authorized evidence and verifying the answer…
              </small>
            </div>
          </div>
        )}
        {answer.isError && (
          <ErrorState
            title="No answer was released"
            detail={answer.error.message}
          />
        )}
      </section>
      <form className="composer surface" onSubmit={submit}>
        <textarea
          aria-label="Ask the SOP Assistant"
          rows={2}
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
          placeholder="Ask about a policy or procedure…"
        />
        <button
          aria-label="Send question"
          disabled={answer.isPending || question.trim().length < 2}
        >
          <ArrowUp />
        </button>
        <small>
          Answers are limited to your authorized, published SOP evidence.
        </small>
      </form>
    </main>
  );
}
