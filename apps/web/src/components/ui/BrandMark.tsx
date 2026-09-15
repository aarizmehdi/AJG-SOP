export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand-mark${compact ? ' brand-mark--compact' : ''}`}>
      <img src="/brand/aziz-jan-trust-logo.png" alt="Aziz Jan Trust" />
    </span>
  );
}
