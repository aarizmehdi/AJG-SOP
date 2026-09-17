import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { viewerSchema } from '../../types/policy';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import { AdminCanonicalReader } from './AdminCanonicalReader';

const scope = {
  departments: { mode: 'all', values: [] },
  locations: { mode: 'all', values: [] },
  roles: { mode: 'all', values: [] },
};
const locator = {
  source_document_id: 'source',
  page_start: 3,
  page_end: 3,
  sheet_name: null,
  cell_range: null,
};
const date = '2026-09-15T00:00:00Z';
const viewer = viewerSchema.parse({
  policy: {
    id: 'policy',
    organization_id: 'ajt',
    title: 'Attendance SOP',
    category: 'HR',
    policy_number: 'HR-01',
    status: 'active',
    active_version_id: 'v1',
    created_at: date,
    updated_at: date,
  },
  version: {
    id: 'v1',
    organization_id: 'ajt',
    policy_id: 'policy',
    version_label: '1',
    status: 'published',
    access: scope,
    source_document_ids: ['source'],
    canonical_document_ids: ['canonical'],
    index_revision: null,
    created_at: date,
    published_at: date,
    effective_date: null,
  },
  versions: [],
  sources: [],
  section_count: 2,
  page_count: 3,
  canonicals: [
    {
      id: 'canonical',
      title: 'Attendance SOP',
      approved: true,
      sections: [
        {
          id: 'general',
          stable_key: 'general',
          heading: '1. General Rules',
          heading_level: 1,
          chapter: 'Chapter 1',
          parent_section_id: null,
          heading_path: ['General Rules'],
          policy_number: 'HR-01',
          source: locator,
          blocks: [
            {
              id: 'intro',
              kind: 'paragraph',
              text: 'Employees follow these rules.',
              list_items: [],
              table: null,
            },
            {
              id: 'steps',
              kind: 'ordered_list',
              text: null,
              list_items: [
                {
                  text: 'Report on time',
                  children: [{ text: 'Notify your supervisor' }],
                },
              ],
              table: null,
            },
            {
              id: 'schedule',
              kind: 'table',
              text: null,
              list_items: [],
              table: {
                caption: 'Working schedule',
                cells: [
                  {
                    row: 0,
                    column: 0,
                    text: 'Day',
                    row_span: 1,
                    column_span: 1,
                    is_header: true,
                  },
                  {
                    row: 0,
                    column: 1,
                    text: 'Hours',
                    row_span: 1,
                    column_span: 1,
                    is_header: true,
                  },
                  {
                    row: 1,
                    column: 0,
                    text: 'Monday',
                    row_span: 1,
                    column_span: 1,
                    is_header: false,
                  },
                  {
                    row: 1,
                    column: 1,
                    text: '9–5',
                    row_span: 1,
                    column_span: 1,
                    is_header: false,
                  },
                ],
              },
            },
          ],
        },
        {
          id: 'hours',
          stable_key: 'hours',
          heading: '1.1 Working Hours',
          heading_level: 2,
          chapter: 'Chapter 1',
          parent_section_id: 'general',
          heading_path: ['General Rules', 'Working Hours'],
          policy_number: null,
          source: locator,
          blocks: [
            {
              id: 'detail',
              kind: 'paragraph',
              text: 'Staff work 9–5.',
              list_items: [],
              table: null,
            },
          ],
        },
      ],
    },
  ],
});

describe('admin canonical SOP reader', () => {
  it('renders structured lists and tables and opens a nested section', () => {
    render(
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: 'admin',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <AdminCanonicalReader viewer={viewer} />
      </LanguageContext>,
    );
    expect(
      screen.getByRole('heading', { name: '1. General Rules' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveTextContent('Monday');
    expect(
      screen.getByRole('columnheader', { name: 'Hours' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Notify your supervisor')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '1.1 Working Hours' }));
    expect(
      screen.getByRole('heading', { name: '1.1 Working Hours' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Staff work 9–5.')).toBeInTheDocument();
  });
});
