import { useRef } from 'react';
import { useOutlet, useLocation } from 'react-router-dom';
import { SwitchTransition, CSSTransition } from 'react-transition-group';

/**
 * Wraps the router <Outlet /> with a smooth fade + slide transition
 * whenever the top-level route path changes.
 */
export function AnimatedOutlet() {
  const location = useLocation();
  const currentOutlet = useOutlet();
  const nodeRef = useRef<HTMLDivElement>(null);

  // Use the first two path segments as the transition key so that
  // sub-routes (e.g. /admin/policies → /admin/add) don't re-trigger
  // the page transition — only top-level nav changes do.
  const transitionKey = location.pathname.split('/').slice(0, 2).join('/');

  return (
    <SwitchTransition mode="out-in">
      <CSSTransition
        key={transitionKey}
        nodeRef={nodeRef}
        timeout={280}
        classNames="page"
        unmountOnExit
      >
        <div ref={nodeRef} className="page-transition">
          {currentOutlet}
        </div>
      </CSSTransition>
    </SwitchTransition>
  );
}
