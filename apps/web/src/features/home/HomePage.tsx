import { ArrowRight, MessageCircle, Search, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function HomePage() {
  return (
    <main className="page home-page">
      <span className="eyebrow">SOP knowledge</span>
      <h1>What would you like to know?</h1>
      <p className="lead">
        Search published policies or ask for a clear explanation grounded in the
        SOPs available to you.
      </p>
      <div className="action-grid">
        <Link to="/search" className="action-card">
          <span className="icon-tile">
            <Search />
          </span>
          <div>
            <h2>Search SOPs</h2>
            <p>Find an exact policy, section, or procedure.</p>
          </div>
          <ArrowRight />
        </Link>
        <Link to="/assistant" className="action-card">
          <span className="icon-tile">
            <MessageCircle />
          </span>
          <div>
            <h2>Ask SOP Assistant</h2>
            <p>Get a concise answer with verified sources.</p>
          </div>
          <ArrowRight />
        </Link>
      </div>
      <div className="trust-note">
        <ShieldCheck />
        <span>
          <strong>Answers stay grounded.</strong> The assistant only uses
          published SOP evidence you are allowed to access.
        </span>
      </div>
    </main>
  );
}
