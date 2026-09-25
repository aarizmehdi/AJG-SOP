import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { AvailablePolicies } from '../home/AvailablePolicies';
import { useLanguage } from '../language/useLanguage';

export default function AvailablePoliciesPage() {
  const { t } = useLanguage();
  return (
    <main className="page available-policies-page">
      <Link className="back-link" to="/home">
        <ArrowLeft aria-hidden="true" /> {t('home')}
      </Link>
      <span className="eyebrow">{t('availableToYou')}</span>
      <h1>{t('allAvailableSops')}</h1>
      <p className="lead">{t('availableSopsLead')}</p>
      <AvailablePolicies />
    </main>
  );
}
