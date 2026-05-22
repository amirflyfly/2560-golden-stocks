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

  await page.route('**/api/v1/scans/*/results**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'OK',
        data: {
          task: {
            id: 'workflow-closure-e2e-scan',
            task_id: 'workflow-closure-e2e-scan',
            strategy_code: '2560',
            status: 'completed',
            market_data: {
              data_quality: 'primary',
              actual_provider: 'e2e_registry',
            },
          },
          status: 'completed',
          page: 1,
          page_size: 20,
          total: 1,
          strategy_runner: 'registry',
          market_data: {
            data_quality: 'primary',
            actual_provider: 'e2e_registry',
            fallback_used: false,
          },
          items: [
            {
              symbol: '000001',
              stock_name: '平安银行',
              name: '平安银行',
              security_type: 'stock',
              bar_interval: '1d',
              interval: '1d',
              strategy_runner: 'registry',
              executable_signal: true,
              signal_type: 'BUY',
              side: 'BUY',
              data_quality: 'primary',
              market_data_source: 'e2e_registry',
              fallback_used: false,
              last_price: 10,
              pick_price: 10,
              explanation: {
                score: 88,
                confidence: 0.91,
                risk_level: 'low',
                reasons: ['E2E registry executable BUY signal'],
                indicators: {
                  signal: 'BUY',
                  strategy_runner: 'registry',
                },
              },
            },
          ],
        },
      }),
    });
  });

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
  await page.getByTestId('scan-result').getByRole('button', { name: '刷新结果' }).click();
  await expect(page.getByTestId('scan-result')).toContainText('primary');
  await expect(page.locator('.scan-result-table').getByText('E2E registry executable BUY signal')).toBeVisible();
  await expect(page.getByRole('button', { name: '模拟买入' }).first()).toBeEnabled();
  const paperSignalResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/apply-signal') && response.request().method() === 'POST'
  ));
  await page.getByRole('button', { name: '模拟买入' }).first().click();
  expect((await paperSignalResponse).status()).toBe(200);

  await page.getByTestId('nav-trading').click();
  await expect(page.getByTestId('paper-trading-page')).toBeVisible();
  await page.locator('#paper-evidence-section summary').click();
  await expect(page.getByTestId('paper-orders-table')).toContainText('000001');
  await expect(page.getByTestId('paper-fills-table')).toContainText('000001');
  const exitResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/evaluate-exits') && response.request().method() === 'POST'
  ));
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByTestId('paper-action-strip').getByRole('button', { name: '检查止盈止损' }).click();
  expect((await exitResponse).status()).toBe(200);

  await page.getByTestId('nav-reports').click();
  await expect(page.getByTestId('reports-page')).toBeVisible();
  await page.getByRole('checkbox', { name: '推送' }).check();
  const reviewResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/reports/daily-review') && response.request().method() === 'POST'
  ));
  await page.getByTestId('daily-review-submit-button').click();
  expect((await reviewResponse).status()).toBe(200);
  await expect(page.getByTestId('daily-review-summary')).toContainText('queued');
  await expect(page.getByTestId('daily-review-summary')).toContainText('卖出评估');

  const deliveriesResponse = await apiRequest(page, '/api/v1/settings/external-push-deliveries?limit=10');
  const deliveries = await jsonData(deliveriesResponse);
  expect(deliveries.stats.total).toBeGreaterThan(0);
  expect(deliveries.items.some((item) => item.channel_id === 'daily-review-e2e')).toBe(true);
});
