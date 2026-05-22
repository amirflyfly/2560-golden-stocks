import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('admin can trigger market sync and snapshot jobs from the data center page', async ({ page }) => {
  await loginFresh(page);
  await page.getByTestId('nav-sync').click();

  await expect(page.getByTestId('market-sync-page')).toBeVisible();
  await expect(page.getByTestId('market-coverage-table')).toBeVisible();
  await expect(page.getByTestId('market-snapshot-table')).toBeVisible();

  const syncResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/market-data/sync') && response.request().method() === 'POST'
  ));
  await page.getByTestId('market-sync-submit-button').click();
  expect((await syncResponse).status()).toBe(202);

  await expect(page.getByTestId('market-snapshot-sync-button')).toBeEnabled();
  const snapshotResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/market-data/snapshots/sync') && response.request().method() === 'POST'
  ));
  await page.getByTestId('market-snapshot-sync-button').click();
  expect((await snapshotResponse).status()).toBe(202);

  await expect(page.getByTestId('market-sync-task-table')).toBeVisible();
  await expect(page.getByTestId('market-sync-system-task-table')).toBeVisible();
  await expect(page.getByTestId('market-sync-manual-task-table')).toBeVisible();
});
