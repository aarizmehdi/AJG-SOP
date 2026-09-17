export function RouteSkeleton({ label = 'Loading page' }: { label?: string }) {
  return (
    <main className="page" aria-busy="true" aria-label={label}>
      <div className="skeleton skeleton--eyebrow" />
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--panel" />
    </main>
  );
}
