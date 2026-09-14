import type { HTMLAttributes } from 'react';

export function Surface({
  className = '',
  ...props
}: HTMLAttributes<HTMLElement>) {
  return <section className={`surface ${className}`} {...props} />;
}
