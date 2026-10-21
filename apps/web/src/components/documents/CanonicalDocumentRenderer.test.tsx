import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  CanonicalDocumentRenderer,
  type CanonicalSectionView,
} from './CanonicalDocumentRenderer';

describe('CanonicalDocumentRenderer source numbering', () => {
  it('preserves skipped, decimal, alphabetic and Roman source markers', () => {
    const sections: CanonicalSectionView[] = [
      {
        id: 'synthetic-section',
        heading: 'Dispatch procedure',
        heading_level: 2,
        source: { page_start: 4 },
        blocks: [
          {
            id: 'clauses',
            kind: 'ordered_list',
            list_items: [
              {
                marker: '5.1.',
                text: 'First source clause',
                children: [
                  { marker: 'a)', text: 'Approval condition' },
                  { marker: 'ii)', text: 'Source exception' },
                ],
              },
              { marker: '10.', text: 'Source numbering skips a clause' },
            ],
          },
        ],
      },
    ];
    const { container } = render(
      <CanonicalDocumentRenderer sections={sections} />,
    );
    expect(screen.getByText('5.1.')).toBeInTheDocument();
    expect(screen.getByText('a)')).toBeInTheDocument();
    expect(screen.getByText('ii)')).toBeInTheDocument();
    expect(screen.getByText('10.')).toBeInTheDocument();
    expect(container.querySelectorAll('ol')).toHaveLength(2);
    expect(
      container.querySelectorAll('.canonical-source-list-item'),
    ).toHaveLength(4);
    expect(container.querySelectorAll('li li')).toHaveLength(2);
  });
});
