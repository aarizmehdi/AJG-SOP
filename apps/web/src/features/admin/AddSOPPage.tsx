import { useMutation, useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  FileImage,
  FileSpreadsheet,
  FileText,
  Upload,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { Button } from '../../components/ui/Button';
import { policyDraftSchema, type AccessScope } from '../../types/policy';
import { profileSchema } from '../../types/profile';
import {
  parserCapabilitiesSchema,
  sourceDocumentSchema,
  type SourceFormat,
} from '../../types/source';
import { AccessScopeEditor } from './AccessScopeEditor';
import { useAdminCopy } from './adminCopy';

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

type PendingDraft = {
  policyId: string;
  versionId: string;
  title: string;
  category: string;
  versionLabel: string;
  access: AccessScope;
  workflow: 'verified_pair' | 'single';
};
const pendingDraftKey = 'ajt-pending-source-import';
function restorePendingDraft(): PendingDraft | null {
  try {
    const stored = sessionStorage.getItem(pendingDraftKey);
    if (!stored) return null;
    const value = JSON.parse(stored) as PendingDraft;
    return value.policyId && value.versionId && value.title ? value : null;
  } catch {
    return null;
  }
}

export default function AddSOPPage() {
  const { copy } = useAdminCopy();
  const [workflow, setWorkflow] = useState<'verified_pair' | 'single'>(
    restorePendingDraft()?.workflow ?? 'verified_pair',
  );
  const [format, setFormat] = useState<SourceFormat>('pdf');
  const [markdownMode, setMarkdownMode] = useState<'file' | 'paste'>('file');
  const [file, setFile] = useState<File | null>(null);
  const [originalFile, setOriginalFile] = useState<File | null>(null);
  const [structuredFile, setStructuredFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [title, setTitle] = useState(restorePendingDraft()?.title ?? '');
  const [category, setCategory] = useState(
    restorePendingDraft()?.category ?? 'Operations',
  );
  const [versionLabel, setVersionLabel] = useState(
    restorePendingDraft()?.versionLabel ?? '1.0',
  );
  const [pendingDraft, setPendingDraft] = useState(restorePendingDraft);
  const [access, setAccess] = useState<AccessScope>(
    restorePendingDraft()?.access ?? {
      departments: { mode: 'selected', values: [] },
      locations: { mode: 'selected', values: [] },
      roles: { mode: 'selected', values: [] },
    },
  );
  const navigate = useNavigate();
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const canIngest =
    profile.data?.application_roles.includes('system_admin') ?? false;
  const capabilities = useQuery({
    queryKey: ['parser-capabilities'],
    queryFn: () =>
      apiRequest('/admin/sources/capabilities', parserCapabilitiesSchema),
    enabled: canIngest,
  });
  const upload = useMutation({
    mutationFn: async () => {
      const draft: PendingDraft =
        pendingDraft ??
        (await apiRequest('/admin/policies', policyDraftSchema, {
          method: 'POST',
          body: JSON.stringify({
            title,
            category,
            version_label: versionLabel,
            access,
          }),
        }).then((created) => {
          const next = {
            policyId: created.policy.id,
            versionId: created.version.id,
            title,
            category,
            versionLabel,
            access,
            workflow,
          };
          sessionStorage.setItem(pendingDraftKey, JSON.stringify(next));
          setPendingDraft(next);
          return next;
        }));
      if (workflow === 'verified_pair') {
        if (!originalFile || !structuredFile)
          throw new Error('Choose both the original PDF and cleaned Markdown');
        const body = new FormData();
        body.set('policy_id', draft.policyId);
        body.set('version_id', draft.versionId);
        body.set('original_file', originalFile);
        body.set('structured_file', structuredFile);
        return apiRequest('/admin/sources/import', sourceDocumentSchema, {
          method: 'POST',
          body,
        });
      }
      const pasteMarkdown = format === 'markdown' && markdownMode === 'paste';
      if (format === 'structured_text' || pasteMarkdown) {
        return apiRequest('/admin/sources/paste', sourceDocumentSchema, {
          method: 'POST',
          body: JSON.stringify({
            policy_id: draft.policyId,
            version_id: draft.versionId,
            title,
            content: text,
            source_format: format,
          }),
        });
      }
      if (!file) throw new Error('Choose a source file');
      const body = new FormData();
      body.set('policy_id', draft.policyId);
      body.set('version_id', draft.versionId);
      body.set('source_format', format);
      body.set('file', file);
      return apiRequest('/admin/sources/upload', sourceDocumentSchema, {
        method: 'POST',
        body,
      });
    },
    onSuccess: (source) => {
      sessionStorage.removeItem(pendingDraftKey);
      setPendingDraft(null);
      void navigate(`/admin/review/${source.id}`);
    },
  });
  const isPaste =
    format === 'structured_text' ||
    (format === 'markdown' && markdownMode === 'paste');
  const accessComplete = Object.values(access).every(
    (dimension) =>
      dimension.mode === 'all' ||
      dimension.values.some((value) => value.trim()),
  );
  const scopeSummary = (
    dimension: AccessScope['departments'],
    allLabel: string,
  ) =>
    dimension.mode === 'all'
      ? allLabel
      : dimension.values.join(', ') || 'Not selected';
  if (profile.isPending) return <RouteSkeleton />;
  if (!canIngest)
    return (
      <ErrorState
        title="System administrator access required"
        detail="Controlled source ingestion is available only to the technical administration team."
      />
    );
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
        {pendingDraft && (
          <div className="pending-draft-notice" role="status">
            <strong>
              {copy.unfinishedDraft}: {pendingDraft.title}
            </strong>
            <span>{copy.resumeDraft}</span>
            <Link to={`/admin/policies/${pendingDraft.policyId}`}>
              {copy.inspectDraft}
            </Link>
          </div>
        )}
        <label>
          Policy title
          <input
            value={title}
            disabled={!!pendingDraft}
            onChange={(event) => {
              setTitle(event.target.value);
            }}
          />
        </label>
        <label>
          Category
          <input
            value={category}
            disabled={!!pendingDraft}
            onChange={(event) => {
              setCategory(event.target.value);
            }}
          />
        </label>
        <label>
          Version
          <input
            value={versionLabel}
            disabled={!!pendingDraft}
            onChange={(event) => {
              setVersionLabel(event.target.value);
            }}
          />
        </label>
      </div>
      <fieldset disabled={!!pendingDraft} className="pending-draft-scope">
        <AccessScopeEditor value={access} onChange={setAccess} />
      </fieldset>
      <section
        className="scope-confirmation surface"
        aria-labelledby="scope-confirmation-title"
      >
        <div>
          <span className="eyebrow">Authorization check</span>
          <h3 id="scope-confirmation-title">
            Who will be able to access this SOP?
          </h3>
          <p>
            These three fields control employee visibility. Category is
            descriptive and does not grant access.
          </p>
        </div>
        <dl>
          <div>
            <dt>Department(s)</dt>
            <dd>{scopeSummary(access.departments, 'All departments')}</dd>
          </div>
          <div>
            <dt>Location(s)</dt>
            <dd>{scopeSummary(access.locations, 'All locations')}</dd>
          </div>
          <div>
            <dt>Organizational role(s)</dt>
            <dd>{scopeSummary(access.roles, 'All organizational roles')}</dd>
          </div>
        </dl>
        <strong className="scope-warning">
          Employees must match Department AND Location AND Organizational Role.
          Confirm the values against production employee profiles before
          ingestion.
        </strong>
      </section>
      <section
        className="source-workflow surface"
        aria-labelledby="source-workflow-title"
      >
        <div>
          <span className="eyebrow">Source workflow</span>
          <h3 id="source-workflow-title">Choose how AJG supplied this SOP</h3>
          <p>
            Keep the authoritative original separate from structured ingestion
            content.
          </p>
        </div>
        <div className="source-workflow-options">
          <button
            type="button"
            disabled={!!pendingDraft}
            className={workflow === 'verified_pair' ? 'selected' : ''}
            aria-pressed={workflow === 'verified_pair'}
            onClick={() => {
              setWorkflow('verified_pair');
            }}
          >
            <strong>Original PDF + cleaned Markdown</strong>
            <span>Preferred verified-document workflow</span>
          </button>
          <button
            type="button"
            disabled={!!pendingDraft}
            className={workflow === 'single' ? 'selected' : ''}
            aria-pressed={workflow === 'single'}
            onClick={() => {
              setWorkflow('single');
            }}
          >
            <strong>Single source or pasted text</strong>
            <span>PDF, scan, DOCX, XLSX, Markdown, image or text</span>
          </button>
        </div>
      </section>
      {workflow === 'single' && (
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
                  setFile(null);
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
      )}
      <div className="upload-panel surface">
        {workflow === 'verified_pair' ? (
          <div className="paired-source-grid">
            <label className="drop-zone paired-source-card">
              <Upload />
              <span className="eyebrow">Original source</span>
              <strong>{originalFile?.name ?? 'Upload original PDF'}</strong>
              <span>
                The authoritative AJG document used for verification and audit.
              </span>
              <input
                type="file"
                accept=".pdf,application/pdf"
                onChange={(event) => {
                  setOriginalFile(event.target.files?.[0] ?? null);
                }}
              />
            </label>
            <label className="drop-zone paired-source-card">
              <FileText />
              <span className="eyebrow">Structured content</span>
              <strong>
                {structuredFile?.name ?? 'Upload cleaned Markdown'}
              </strong>
              <span>
                Human-reviewed structured content used to create the canonical
                SOP.
              </span>
              <input
                type="file"
                accept=".md,.markdown,text/markdown"
                onChange={(event) => {
                  setStructuredFile(event.target.files?.[0] ?? null);
                }}
              />
            </label>
          </div>
        ) : (
          format === 'markdown' && (
            <>
              <div className="form-actions" aria-label="Markdown input method">
                <Button
                  variant={markdownMode === 'file' ? 'primary' : 'secondary'}
                  onClick={() => {
                    setMarkdownMode('file');
                  }}
                >
                  Upload .md file
                </Button>
                <Button
                  variant={markdownMode === 'paste' ? 'primary' : 'secondary'}
                  onClick={() => {
                    setMarkdownMode('paste');
                  }}
                >
                  Paste Markdown
                </Button>
              </div>
              <p className="field-help">
                Optional metadata: title, policy_number and effective_date in a
                leading --- block. Dates use YYYY-MM-DD.
              </p>
            </>
          )
        )}
        {workflow === 'single' &&
          (isPaste ? (
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
                    ? '---\ntitle: Policy title\npolicy_number: SOP-76\neffective_date: 2026-09-25\n---\n# Policy title\n\n## 1. Section'
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
                accept={
                  format === 'markdown'
                    ? '.md,.markdown,text/markdown'
                    : undefined
                }
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                }}
              />
            </label>
          ))}
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
              !accessComplete ||
              (workflow === 'verified_pair'
                ? !originalFile || !structuredFile
                : isPaste
                  ? !text.trim()
                  : !file)
            }
            onClick={() => {
              upload.mutate();
            }}
          >
            {upload.isPending
              ? 'Preserving source…'
              : workflow === 'verified_pair'
                ? 'Import and build canonical SOP'
                : 'Upload and extract'}
          </Button>
        </div>
      </div>
    </section>
  );
}
