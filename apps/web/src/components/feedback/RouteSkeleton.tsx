export function RouteSkeleton() {
  return (
    <main className="page" aria-busy="true" aria-label="Loading page">
      <div className="skeleton skeleton--eyebrow" />
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--panel" />
    </main>
  );
}
