export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: 'Published',
    published: 'Published',
    draft: 'Draft',
    uploaded: 'Processing',
    processing: 'Processing',
    extraction_review: 'Review Required',
    review_required: 'Review Required',
    ready_for_indexing: 'Ready for Review',
    indexing: 'Processing',
    ready_to_publish: 'Ready for Review',
    approved: 'Ready for Review',
    failed: 'Failed',
    superseded: 'Superseded',
    inactive: 'Inactive / Archived',
  };
  return labels[status] ?? 'Draft';
}
export function sourceLabel(format: string): string {
  // Source types describe the uploaded document, independently of parser choice.
  const labels: Record<string, string> = {
    pdf: 'PDF',
    scanned_pdf: 'Scanned PDF',
    image: 'Image',
    docx: 'DOCX',
    xlsx: 'XLSX',
    markdown: 'Markdown',
    structured_text: 'Text',
  };
  return labels[format] ?? format.toUpperCase();
}
export function documentStatus(
  versionStatus: string,
  sourceStatuses: string[],
  policyStatus?: string,
): string {
  if (policyStatus === 'inactive') return 'Inactive / Archived';
  if (versionStatus === 'published' || versionStatus === 'superseded')
    return statusLabel(versionStatus);
  if (versionStatus === 'failed' || sourceStatuses.includes('failed'))
    return 'Failed';
  if (sourceStatuses.includes('review_required')) return 'Review Required';
  if (
    sourceStatuses.includes('processing') ||
    sourceStatuses.includes('uploaded')
  )
    return 'Processing';
  return statusLabel(versionStatus);
}
export function formatDate(
  value: string | null | undefined,
  language: 'english' | 'urdu' | 'roman_urdu' = 'english',
): string {
  if (!value || Number.isNaN(Date.parse(value))) return '—';
  return new Intl.DateTimeFormat(language === 'urdu' ? 'ur-PK' : 'en-PK', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value));
}
export function displayVersion(
  label: string | undefined,
  prefix = 'Version',
  empty = 'No version',
): string {
  if (!label) return empty;
  return /^v(?:ersion)?\s/i.test(label)
    ? label.replace(/^v(?:ersion)?\s*/i, `${prefix} `)
    : `${prefix} ${label}`;
}
