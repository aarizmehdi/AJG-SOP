import { ArrowRight, MessageCircle, Search, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../language/useLanguage';
import { AvailablePolicies } from './AvailablePolicies';

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
      <section className="home-policies" aria-labelledby="available-sops-title">
        <div className="home-policies-heading">
          <div>
            <span className="eyebrow">{t('availableToYou')}</span>
            <h2 id="available-sops-title">{t('mySops')}</h2>
          </div>
          <Link to="/policies" className="text-link">
            {t('viewAllSops')} <ArrowRight aria-hidden="true" />
          </Link>
        </div>
        <AvailablePolicies limit={3} />
      </section>
    </main>
  );
}
