import { expect, test } from '@playwright/test';
import { apiRequest, jsonData } from './helpers/api.js';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('admin can run the quant workflow closure through pages', async ({ page }) => {
  await loginFresh(page);

  const channelResponse = await apiRequest(page, '/api/v1/settings/external-push-channels', {
    method: 'POST',
    body: {
      id: 'daily-review-e2e',
      name: 'Daily Review E2E',
      type: 'webhook',
      enabled: true,
      config: { webhook_url: 'https://alerts.example.com/daily-review' },
    },
  });
  expect(channelResponse.status()).toBe(201);

  await page.getByTestId('nav-sync').click();
  await expect(page.getByTestId('market-sync-page')).toBeVisible();
  const syncResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/market-data/sync') && response.request().method() === 'POST'
  ));
  await page.getByTestId('market-sync-submit-button').click();
  expect((await syncResponse).status()).toBe(202);
  const snapshotResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/market-data/snapshots/sync') && response.request().method() === 'POST'
  ));
  await page.getByTestId('market-snapshot-sync-button').click();
  expect((await snapshotResponse).status()).toBe(202);

  await page.getByTestId('nav-scans').click();
  const scanResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/scans') && response.request().method() === 'POST'
  ));
  await page.getByTestId('create-scan-button').click();
  expect((await scanResponse).status()).toBe(202);
  await expect(page.getByTestId('scan-result')).toContainText('primary');

  await page.getByTestId('nav-trading').click();
  await expect(page.getByTestId('paper-trading-page')).toBeVisible();
  const exitResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/evaluate-exits') && response.request().method() === 'POST'
  ));
  await page.getByTestId('paper-evaluate-exits-button').click();
  expect((await exitResponse).status()).toBe(200);

  await page.getByTestId('nav-reports').click();
  await expect(page.getByTestId('reports-page')).toBeVisible();
  await page.locator('input[type="checkbox"]').check();
  const reviewResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/reports/daily-review') && response.request().method() === 'POST'
  ));
  await page.getByTestId('daily-review-submit-button').click();
  expect((await reviewResponse).status()).toBe(200);
  await expect(page.getByTestId('daily-review-summary')).toContainText('queued');

  const deliveriesResponse = await apiRequest(page, '/api/v1/settings/external-push-deliveries?limit=10');
  const deliveries = await jsonData(deliveriesResponse);
  expect(deliveries.stats.total).toBeGreaterThan(0);
  expect(deliveries.items.some((item) => item.channel_id === 'daily-review-e2e')).toBe(true);
});
