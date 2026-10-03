import { expect, test } from '@playwright/test';

async function openAssistant(page: import('@playwright/test').Page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto('/assistant');
    try {
      await page
        .getByRole('textbox', { name: /Ask the SOP Assistant/i })
        .or(page.getByRole('heading', { name: 'Choose your language' }))
        .first()
        .waitFor({ state: 'visible', timeout: 12_000 });
      break;
    } catch (error) {
      if (attempt === 2) throw error;
    }
  }
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
    await page.goto('/assistant');
  }
  await page
    .getByRole('textbox', { name: /Ask the SOP Assistant/i })
    .waitFor({ state: 'visible', timeout: 30_000 });
}

for (const width of [1440, 1366, 390]) {
  test(`assistant conversation and reset at ${String(width)}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => {
      localStorage.setItem('ajt-fixture-identity', 'employee');
    });
    await openAssistant(page);
    const composer = page.getByRole('textbox', {
      name: /Ask the SOP Assistant/i,
    });
    await expect(composer).toBeVisible();
    await composer.fill('Hi');
    await composer.press('Enter');
    await expect(page.getByText(/I can help you find guidance/i)).toBeVisible();
    await composer.fill('How is damaged stock handled?');
    await composer.press('Enter');
    await expect(page.getByText(/synthetic fixture content/i)).toBeVisible();
    await expect(
      page.getByRole('link', { name: /SYNTHETIC FIXTURE/i }),
    ).toBeVisible();
    await composer.fill('What about the damaged item?');
    await composer.press('Enter');
    await expect(page.locator('.turn')).toHaveCount(3);
    await expect(page.locator('.assistant-failure')).toHaveCount(0);
    if (width === 390) {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      expect(overflow).toBe(false);
    }
    await page.reload();
    await expect(page.getByText('How can I help with an SOP?')).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('.turn')).toHaveCount(0);
  });
}

test('long verified Markdown and sources stay readable on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem('ajt-fixture-identity', 'employee');
  });
  await page.route('**/api/v1/assistant/answer/events', async (route) => {
    const citation = {
      chunk_id: 'fixture-chunk',
      policy_id: 'fixture-policy',
      policy_title: 'SYNTHETIC FIXTURE — Store Operations SOP',
      section_id: 'damage',
      heading_path: ['Store Operations', 'Damaged Stock Handling'],
      document_id: 'fixture-source',
      source: {
        source_document_id: 'fixture-source',
        page_start: 4,
        page_end: 4,
        sheet_name: null,
        cell_range: null,
        block_anchor: null,
      },
    };
    const answer = `### Procedure\n\n**Damaged stock:** ${'Isolate and record the item. '.repeat(35)}\n\n1. Separate it.\n2. Record it.\n\n| Step | Action |\n| --- | --- |\n| 1 | Isolate |\n| 2 | Record |`;
    const event = (name: string, data: unknown) =>
      `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
    await route.fulfill({
      contentType: 'text/event-stream',
      body:
        event('answer_start', {
          kind: 'policy_answer',
          answerable: true,
          language: 'english',
          verified: true,
        }) +
        event('answer_delta', { text: answer }) +
        event('sources', { citations: [citation] }) +
        event('done', { verified: true }),
    });
  });
  await openAssistant(page);
  const composer = page.getByRole('textbox', {
    name: /Ask the SOP Assistant/i,
  });
  await composer.fill('How is damaged stock handled?');
  await composer.press('Enter');
  await expect(page.getByRole('heading', { name: 'Procedure' })).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(
    page.getByRole('link', { name: /SYNTHETIC FIXTURE/i }),
  ).toHaveAttribute('href', /section=damage/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
