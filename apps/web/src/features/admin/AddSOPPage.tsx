import { useMutation, useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  FileImage,
  FileSpreadsheet,
  FileText,
  Upload,
} from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { Button } from '../../components/ui/Button';
import { policyDraftSchema, type AccessScope } from '../../types/policy';
import {
  parserCapabilitiesSchema,
  sourceDocumentSchema,
  type SourceFormat,
} from '../../types/source';
import { AccessScopeEditor } from './AccessScopeEditor';

const formats: {
  id: SourceFormat;
  label: string;
  note: string;
  icon: typeof FileText;
}[] = [
  { id: 'pdf', label: 'PDF', note: 'Native text PDF', icon: FileText },
  {
    id: 'scanned_pdf',
    label: 'Scanned PDF',
    note: 'OCR provider required',
    icon: FileImage,
  },
  {
    id: 'image',
    label: 'Scan / Image',
    note: 'PNG, JPG or TIFF',
    icon: FileImage,
  },
  { id: 'docx', label: 'Word', note: 'DOCX document', icon: FileText },
  {
    id: 'xlsx',
    label: 'Excel',
    note: 'Sheets and cells',
    icon: FileSpreadsheet,
  },
  {
    id: 'markdown',
    label: 'Markdown',
    note: 'Structured Markdown',
    icon: FileText,
  },
  {
    id: 'structured_text',
    label: 'Paste text',
    note: 'Structured policy text',
    icon: FileText,
  },
];

export default function AddSOPPage() {
  const [format, setFormat] = useState<SourceFormat>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('Operations');
  const [versionLabel, setVersionLabel] = useState('1.0');
  const [access, setAccess] = useState<AccessScope>({
    departments: { mode: 'selected', values: ['store'] },
    locations: { mode: 'selected', values: ['peshawar-main'] },
    roles: { mode: 'selected', values: ['store_keeper'] },
  });
  const navigate = useNavigate();
  const capabilities = useQuery({
    queryKey: ['parser-capabilities'],
    queryFn: () =>
      apiRequest('/admin/sources/capabilities', parserCapabilitiesSchema),
  });
  const upload = useMutation({
    mutationFn: async () => {
      const draft = await apiRequest('/admin/policies', policyDraftSchema, {
        method: 'POST',
        body: JSON.stringify({
          title,
          category,
          version_label: versionLabel,
          access,
        }),
      });
      if (format === 'structured_text' || format === 'markdown') {
        return apiRequest('/admin/sources/paste', sourceDocumentSchema, {
          method: 'POST',
          body: JSON.stringify({
            policy_id: draft.policy.id,
            version_id: draft.version.id,
            title,
            content: text,
            source_format: format,
          }),
        });
      }
      if (!file) throw new Error('Choose a source file');
      const body = new FormData();
      body.set('policy_id', draft.policy.id);
      body.set('version_id', draft.version.id);
      body.set('source_format', format);
      body.set('file', file);
      return apiRequest('/admin/sources/upload', sourceDocumentSchema, {
        method: 'POST',
        body,
      });
    },
    onSuccess: (source) => {
      void navigate(`/admin/review/${source.id}`);
    },
  });
  const isText = format === 'structured_text' || format === 'markdown';
  return (
    <section className="admin-content add-sop">
      <div className="section-heading">
        <div>
          <h2>Add a source document</h2>
          <p>
            Originals remain private and every extraction requires human review.
          </p>
        </div>
        <span className="step-label">Step 1 of 4</span>
      </div>
      <div className="metadata-grid surface">
        <label>
          Policy title
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
            }}
          />
        </label>
        <label>
          Category
          <input
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
            }}
          />
        </label>
        <label>
          Version
          <input
            value={versionLabel}
            onChange={(event) => {
              setVersionLabel(event.target.value);
            }}
          />
        </label>
      </div>
      <AccessScopeEditor value={access} onChange={setAccess} />
      <div className="format-grid">
        {formats.map(({ id, label, note, icon: Icon }) => {
          const capability = capabilities.data?.find(
            (item) => item.source_format === id,
          );
          return (
            <button
              key={id}
              className={`format-card${format === id ? ' selected' : ''}`}
              onClick={() => {
                setFormat(id);
              }}
            >
              <Icon />
              <strong>{label}</strong>
              <span>
                {capability
                  ? `${capability.available ? capability.provider : 'Provider required'} · ${capability.detail}`
                  : note}
              </span>
              {format === id && <CheckCircle2 className="selected-check" />}
            </button>
          );
        })}
      </div>
      <div className="upload-panel surface">
        {isText ? (
          <>
            <label htmlFor="source-text">Policy content</label>
            <textarea
              id="source-text"
              rows={12}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
              }}
              placeholder={
                format === 'markdown'
                  ? '# Policy title\n\n## 1. Section'
                  : 'Paste the structured policy text here…'
              }
            />
          </>
        ) : (
          <label className="drop-zone">
            <Upload />
            <strong>{file?.name ?? 'Choose the original source file'}</strong>
            <span>
              The source is hashed and stored privately before processing.
            </span>
            <input
              type="file"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
              }}
            />
          </label>
        )}
        {upload.isError && (
          <ErrorState title="Upload failed" detail={upload.error.message} />
        )}
        <div className="form-actions">
          <Button
            variant="secondary"
            onClick={() => {
              void navigate('/admin');
            }}
          >
            Cancel
          </Button>
          <Button
            disabled={
              upload.isPending ||
              !title.trim() ||
              (isText ? !text.trim() : !file)
            }
            onClick={() => {
              upload.mutate();
            }}
          >
            {upload.isPending ? 'Preserving source…' : 'Upload and extract'}
          </Button>
        </div>
      </div>
    </section>
  );
}
