const english = {
  heading: 'Danger Zone',
  explain:
    'Archive keeps a policy for future recovery. Permanent deletion removes its stored sources and retrieval data.',
  action: 'Permanently delete policy',
  previewing: 'Checking stored policy resources…',
  published: 'Currently published',
  yes: 'Yes',
  no: 'No',
  resources: {
    policies: 'Policies',
    policy_versions: 'Versions',
    source_documents: 'Sources',
    canonical_sops: 'Canonical documents',
    raw_parser_results: 'Raw parser records',
    ingestion_jobs: 'Ingestion jobs',
    retrieval_chunks: 'Retrieval chunks',
  },
  other: 'Other exact linked records',
  objects: 'Source objects',
  bytes: 'Source bytes',
  vectors: 'Pinecone vectors',
  warning:
    'This permanently removes the policy and all of its stored source and retrieval data. This action cannot be undone.',
  history:
    'Historical chat text has no stored citation provenance and cannot be associated with this policy. Unrelated chat history is retained.',
  typeTitle: 'Type the exact policy title',
  typePhrase: 'Type DELETE PERMANENTLY',
  confirm: 'Delete permanently',
  deleting: 'Deleting and verifying…',
  cancel: 'Cancel',
  success:
    'Policy and all associated source and retrieval data permanently deleted.',
  failed:
    'Cleanup is incomplete. The policy is blocked from retrieval. Retry to finish the remaining stages.',
};
const urdu: typeof english = {
  heading: 'مستقل حذف',
  explain:
    'آرکائیو میں پالیسی محفوظ رہتی ہے۔ مستقل حذف سے اصل فائلیں اور تلاش کا ڈیٹا ختم ہو جاتا ہے۔',
  action: 'پالیسی مستقل حذف کریں',
  previewing: 'محفوظ وسائل کی جانچ جاری ہے…',
  published: 'اس وقت شائع شدہ',
  yes: 'ہاں',
  no: 'نہیں',
  resources: {
    policies: 'پالیسیاں',
    policy_versions: 'ورژن',
    source_documents: 'ماخذ',
    canonical_sops: 'منظم دستاویزات',
    raw_parser_results: 'خام استخراج',
    ingestion_jobs: 'پروسیسنگ ریکارڈ',
    retrieval_chunks: 'تلاش کے حصے',
  },
  other: 'دیگر منسلک ریکارڈ',
  objects: 'ماخذ فائلیں',
  bytes: 'فائلوں کا حجم (بائٹس)',
  vectors: 'Pinecone ویکٹرز',
  warning:
    'اس عمل سے پالیسی، اس کی تمام محفوظ فائلیں اور تلاش کا ڈیٹا مستقل ختم ہو جائے گا۔ یہ عمل واپس نہیں ہو سکتا۔',
  history:
    'پرانے چیٹ متن میں حوالوں کی شناخت محفوظ نہیں ہے، اس لیے اسے اس پالیسی سے منسوب نہیں کیا جا سکتا۔ غیر متعلقہ چیٹ محفوظ رہے گی۔',
  typeTitle: 'پالیسی کا عین عنوان درج کریں',
  typePhrase: 'DELETE PERMANENTLY درج کریں',
  confirm: 'مستقل حذف کریں',
  deleting: 'حذف اور تصدیق جاری ہے…',
  cancel: 'منسوخ',
  success: 'پالیسی اور اس کی تمام فائلیں اور تلاش کا ڈیٹا مستقل حذف ہو گیا ہے۔',
  failed:
    'صفائی نامکمل ہے۔ پالیسی کی تلاش روک دی گئی ہے۔ باقی مراحل مکمل کرنے کے لیے دوبارہ کوشش کریں۔',
};
const roman: typeof english = {
  heading: 'Mustaqil deletion',
  explain:
    'Archive se policy mehfooz rehti hai. Mustaqil deletion se asal files aur search data khatam ho jata hai.',
  action: 'Policy mustaqil delete karein',
  previewing: 'Mehfooz resources check ho rahe hain…',
  published: 'Abhi published',
  yes: 'Haan',
  no: 'Nahi',
  resources: {
    policies: 'Policies',
    policy_versions: 'Versions',
    source_documents: 'Sources',
    canonical_sops: 'Structured documents',
    raw_parser_results: 'Raw parser records',
    ingestion_jobs: 'Processing records',
    retrieval_chunks: 'Search chunks',
  },
  other: 'Doosray linked records',
  objects: 'Source files',
  bytes: 'Source bytes',
  vectors: 'Pinecone vectors',
  warning:
    'Is se policy, us ki tamam mehfooz source files aur search data mustaqil khatam ho jayega. Yeh action wapas nahi ho sakta.',
  history:
    'Purani chat mein citation IDs mehfooz nahi hain, is liye usay is policy se link nahi kar sakte. Ghair mutaliqa chats mehfooz rahengi.',
  typeTitle: 'Policy ka bilkul sahi title likhein',
  typePhrase: 'DELETE PERMANENTLY likhein',
  confirm: 'Mustaqil delete karein',
  deleting: 'Delete aur verify ho raha hai…',
  cancel: 'Cancel',
  success:
    'Policy aur us ki tamam source files aur search data mustaqil delete ho gaya hai.',
  failed:
    'Cleanup adhura hai. Policy search se block hai. Baqi stages poori karne ke liye dobara koshish karein.',
};
export const purgeCopy = { english, urdu, roman_urdu: roman };
