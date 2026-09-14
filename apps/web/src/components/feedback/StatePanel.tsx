import { AlertCircle, FileQuestion } from 'lucide-react';

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="state-panel">
      <FileQuestion />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}

export function ErrorState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertCircle />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
