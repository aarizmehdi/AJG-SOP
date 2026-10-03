import { expect, test } from '@playwright/test';

const api = 'http://127.0.0.1:8000/api/v1';
const admin = { Authorization: 'Fixture system-admin' };

function largeValidPdf(): Buffer {
  const parts: Buffer[] = [];
  const offsets = [0];
  let length = 0;
  const add = (value: string | Buffer) => {
    const buffer = typeof value === 'string' ? Buffer.from(value) : value;
    parts.push(buffer);
    length += buffer.length;
  };
  const object = (id: number, content: string) => {
    offsets[id] = length;
    add(`${String(id)} 0 obj\n${content}\nendobj\n`);
  };
  add('%PDF-1.4\n');
  add(Buffer.alloc(21 * 1024 * 1024, 32));
  add('\n');
  object(1, '<< /Type /Catalog /Pages 2 0 R >>');
  object(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
  object(
    3,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>',
  );
  object(4, '<< /Length 0 >>\nstream\n\nendstream');
  const xref = length;
  add('xref\n0 5\n0000000000 65535 f \n');
  for (let id = 1; id <= 4; id += 1)
    add(`${String(offsets[id]).padStart(10, '0')} 00000 n \n`);
  add(`trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF`);
  return Buffer.concat(parts);
}

function longMarkdown(): string {
  const sections = Array.from({ length: 36 }, (_, index) => {
    const number = index + 25;
    return (
      `## SOP #${String(number)} Procedure ${String(index + 1)}\n\n` +
      `**AJG procedure ${String(index + 1)}** applies to this section. ` +
      'Keep the original wording visible during review. '.repeat(12) +
      '\n\n1. Confirm the source record.\n  1. Review the nested action.\n' +
      '2. Record the result.\n\n| Role | Action |\n| --- | --- |\n' +
      '| Administrator | Compare source and canonical |\n'
    );
  });
  return `# Store, Excise & Gate SOP — Part 1\n\n${sections.join('\n')}`;
}

test('large paired SOP review stays bounded and follows publication lifecycle', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  const created = await request.post(`${api}/admin/policies`, {
    headers: admin,
    data: {
      title: 'Store, Excise & Gate SOP — Part 1',
      category: 'Operations',
      version_label: '1.0',
      access: {
        departments: { mode: 'all' },
        locations: { mode: 'all' },
        roles: { mode: 'all' },
      },
    },
  });
  expect(created.status()).toBe(201);
  const draft = (await created.json()) as {
    policy: { id: string };
    version: { id: string };
  };
  const imported = await request.post(`${api}/admin/sources/import`, {
    headers: admin,
    multipart: {
      policy_id: draft.policy.id,
      version_id: draft.version.id,
      original_file: {
        name: 'AJG-original.pdf',
        mimeType: 'application/pdf',
        buffer: largeValidPdf(),
      },
      structured_file: {
        name: 'AJG-cleaned.md',
        mimeType: 'text/markdown',
        buffer: Buffer.from(longMarkdown()),
      },
    },
    timeout: 90_000,
  });
  expect(imported.status()).toBe(201);
  const source = (await imported.json()) as { id: string };

  await page.addInitScript(() => {
    if (location.origin === 'http://127.0.0.1:5173')
      localStorage.setItem('ajt-fixture-identity', 'system-admin');
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/admin/review/${source.id}`);
  await page
    .getByRole('heading', { name: 'Choose your language' })
    .or(page.locator('.review-canonical-preview .canonical-section').first())
    .first()
    .waitFor({ state: 'visible', timeout: 30_000 });
  if (
    await page
      .getByRole('heading', { name: 'Choose your language' })
      .isVisible()
  ) {
    await page.getByRole('button', { name: 'Save and continue' }).click();
    await expect
      .poll(() =>
        page.evaluate(() => {
          const key = localStorage.getItem('ajt-active-language-profile');
          return key ? localStorage.getItem(key) : null;
        }),
      )
      .toBe('english');
    await page.goto(`/admin/review/${source.id}`);
  }
  await expect(
    page.locator('.review-canonical-preview .canonical-section'),
  ).toHaveCount(36, { timeout: 30_000 });
  await expect(page.locator('iframe.source-object')).toBeVisible();
  await expect(page.locator('.source-object')).toHaveAttribute(
    'src',
    /original\/stream\?/,
  );

  const desktop = await page.evaluate(() => ({
    pageHeight: document.documentElement.scrollHeight,
    viewport: innerHeight,
    sourceHeight:
      document.querySelector('.source-object')?.getBoundingClientRect()
        .height ?? 0,
    canonicalScroll:
      document.querySelector('.review-canonical-preview')?.scrollHeight ?? 0,
    canonicalHeight:
      document.querySelector('.review-canonical-preview')?.clientHeight ?? 0,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
  }));
  expect(desktop.pageHeight).toBeLessThan(desktop.viewport * 2);
  expect(desktop.sourceHeight).toBeGreaterThan(200);
  expect(desktop.sourceHeight).toBeLessThan(900);
  expect(desktop.canonicalScroll).toBeGreaterThan(desktop.canonicalHeight);
  expect(desktop.horizontalOverflow).toBe(false);
  await page.screenshot({ path: 'test-results/review-desktop.png' });

  await page
    .getByRole('navigation', { name: 'Structured SOP contents' })
    .getByRole('button', { name: 'SOP #60 Procedure 36' })
    .click();
  await expect
    .poll(() =>
      page
        .locator('.review-canonical-preview')
        .evaluate((node) => (node as HTMLElement).scrollTop),
    )
    .toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Edit canonical content' }).click();
  await expect(page.locator('.section-editor')).toHaveCount(1);
  await page.getByRole('button', { name: 'Save correction' }).click();
  await expect(
    page.getByRole('button', { name: 'Submit review' }),
  ).toBeDisabled();

  await page.setViewportSize({ width: 1366, height: 768 });
  const laptop = await page.evaluate(() => ({
    height: document.documentElement.scrollHeight,
    pdf:
      document.querySelector('.source-object')?.getBoundingClientRect()
        .height ?? 0,
  }));
  expect(laptop.height).toBeLessThan(1600);
  expect(laptop.pdf).toBeLessThan(800);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await page.evaluate(() => ({
    height: document.documentElement.scrollHeight,
    overflow: document.documentElement.scrollWidth > innerWidth,
  }));
  expect(mobile.height).toBeLessThan(2500);
  expect(mobile.overflow).toBe(false);
  await page.screenshot({
    path: 'test-results/review-mobile.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole('checkbox', { name: /I confirm that I compared/ })
    .check();
  await page.getByRole('button', { name: 'Submit review' }).click();
  await expect(
    page.getByRole('button', { name: 'Prepare search index' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Prepare search index' }).click();
  await expect(page.getByRole('button', { name: 'Publish' })).toBeVisible();
  await page.getByRole('button', { name: 'Publish' }).click();
  await expect(
    page.getByText('Published', { exact: true }).first(),
  ).toBeVisible();
  await page.goto(`/admin/policies/${draft.policy.id}`);
  await expect(
    page.getByRole('heading', { name: 'Store, Excise & Gate SOP — Part 1' }),
  ).toBeVisible();
  await expect(page.locator('.admin-reader-drawer')).toHaveCount(0);
  await expect(page.locator('.admin-details-drawer')).toHaveCount(0);
  await page.getByRole('button', { name: 'Contents' }).click();
  await expect(page.locator('.admin-reader-drawer')).toBeVisible();
  await page
    .locator('.admin-reader-drawer')
    .getByRole('button', { name: 'SOP #60 Procedure 36' })
    .click();
  await expect(page.locator('.admin-reader-drawer')).toHaveCount(0);
  await page.getByRole('button', { name: 'Document information' }).click();
  await expect(page.locator('.admin-details-drawer')).toContainText(
    'AJG-original.pdf',
  );
  await expect(page.locator('.admin-details-drawer')).not.toContainText(
    'Policy number',
  );
  await page
    .locator('.admin-details-drawer')
    .getByRole('button', { name: 'Collapse' })
    .click();
  await page.getByRole('button', { name: 'Original Document' }).click();
  await expect(page.locator('iframe.source-object')).toBeVisible();
  await expect(page.locator('.original-file')).toContainText('AJG-cleaned.md');
  expect(errors).toEqual([]);
});
