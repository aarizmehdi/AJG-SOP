import { ArrowRight, MessageCircle, Search, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../language/useLanguage';

export default function HomePage() {
  const { t } = useLanguage();
  return (
    <main className="page home-page">
      <span className="eyebrow">{t('homeEyebrow')}</span>
      <h1>{t('homeTitle')}</h1>
      <p className="lead">{t('homeLead')}</p>
      <div className="action-grid">
        <Link to="/search" className="action-card">
          <span className="icon-tile">
            <Search />
          </span>
          <div>
            <h2>{t('searchNav')}</h2>
            <p>{t('homeSearchDetail')}</p>
          </div>
          <ArrowRight />
        </Link>
        <Link to="/assistant" className="action-card">
          <span className="icon-tile">
            <MessageCircle />
          </span>
          <div>
            <h2>{t('homeAssistantTitle')}</h2>
            <p>{t('homeAssistantDetail')}</p>
          </div>
          <ArrowRight />
        </Link>
      </div>
      <div className="trust-note">
        <ShieldCheck />
        <span>
          <strong>{t('homeTrustTitle')}</strong> {t('homeTrustDetail')}
        </span>
      </div>
    </main>
  );
}
