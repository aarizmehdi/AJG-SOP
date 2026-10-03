import { expect, test } from '@playwright/test';
const api = 'http://127.0.0.1:8000/api/v1';
const admin = { Authorization: 'Fixture system-admin' };
test('System Admin previews and permanently purges an SOP on desktop and mobile', async ({
  page,
  request,
}) => {
  const created = await request.post(`${api}/admin/policies`, {
    headers: admin,
    data: {
      title: 'AJG permanent purge browser test',
      category: 'Operations',
      version_label: '1',
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
  const source = await request.post(`${api}/admin/sources/paste`, {
    headers: admin,
    data: {
      policy_id: draft.policy.id,
      version_id: draft.version.id,
      title: 'AJG browser source',
      content:
        '# AJG permanent purge browser test\n## Policy 100\nBrowser fixture retained wording.',
      source_format: 'markdown',
    },
  });
  expect(source.status()).toBe(201);
  const sourceId = ((await source.json()) as { id: string }).id;
  await page.addInitScript(() => {
    localStorage.setItem('ajt-fixture-identity', 'system-admin');
    localStorage.setItem(
      'ajt-active-language-profile',
      'ajt-language:ajt:user-system-admin',
    );
    localStorage.setItem('ajt-language:ajt:user-system-admin', 'english');
  });
  await page.goto(`/admin/policies/${draft.policy.id}`);
  await page.getByRole('button', { name: 'Permanently delete policy' }).click();
  const zone = page.getByRole('region', { name: 'Danger Zone' });
  await expect(zone.getByText('Pinecone vectors')).toBeVisible();
  await expect(
    zone.getByRole('button', { name: 'Delete permanently' }),
  ).toBeDisabled();
  await page.screenshot({
    path: 'test-results/purge-desktop.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(zone.getByLabel('Type the exact policy title')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: 'test-results/purge-mobile.png',
    fullPage: true,
  });
  await zone
    .getByLabel('Type the exact policy title')
    .fill('AJG permanent purge browser test');
  await zone.getByLabel('Type DELETE PERMANENTLY').fill('DELETE PERMANENTLY');
  await zone.getByRole('button', { name: 'Delete permanently' }).click();
  await expect(page).toHaveURL(/\/admin\/policies$/);
  const list = await request.get(`${api}/admin/policies`, { headers: admin });
  expect(
    ((await list.json()) as { id: string }[]).some(
      (p) => p.id === draft.policy.id,
    ),
  ).toBe(false);
  expect(
    (
      await request.get(`${api}/admin/policies/${draft.policy.id}/viewer`, {
        headers: admin,
      })
    ).status(),
  ).toBe(404);
  expect(
    (
      await request.get(`${api}/admin/sources/${sourceId}/review`, {
        headers: admin,
      })
    ).status(),
  ).toBe(404);
});
