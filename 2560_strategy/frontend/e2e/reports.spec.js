import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

async function mockReportsPageData(page) {
  await page.route('**/api/v1/reports/summary?*', async (route) => {
    await route.fulfill({
      json: {
        code: 0,
        data: {
          summary: {
            total_picks: 4,
            review_rate: 0.75,
            deal_count: 2,
            win_rate: 0.5,
            average_return_pct: 3.25,
            high_risk_rate: 0.1,
            data_quality: {
              primary_rate: 1,
              fallback: 0,
              mock: 0,
            },
          },
          groups: [
            {
              strategy: 'FIRST_LIMIT_UP',
              total: 4,
              review_rate: 0.75,
              deals: 2,
              win_rate: 0.5,
              average_return_pct: 3.25,
              high_risk_rate: 0.1,
              data_quality: { primary: 4, fallback: 0, mock: 0, unknown: 0 },
              drilldowns: {},
            },
          ],
        },
      },
    });
  });

  await page.route('**/api/v1/reports?*', async (route) => {
    await route.fulfill({
      json: {
        code: 0,
        data: {
          items: [],
          total: 0,
        },
      },
    });
  });

  await page.route('**/api/v1/settings/external-push-deliveries?*', async (route) => {
    await route.fulfill({
      json: {
        code: 0,
        data: {
          stats: {
            failed: 1,
            queued: 2,
            sent: 3,
          },
          items: [
            {
              id: 'delivery-failed-1',
              delivery_key: 'daily-review:1',
              status: 'failed',
              channel_type: 'webhook',
              channel_id: 'daily-review-webhook',
              task_id: 'task-retry-1',
              retry_count: 2,
              last_error: 'HTTP 500 from downstream',
              updated_at: '2026-05-06T09:30:00Z',
            },
            {
              id: 'delivery-sent-1',
              delivery_key: 'daily-review:2',
              status: 'sent',
              channel_type: 'email',
              channel_id: 'ops-email',
              task_id: 'task-sent-1',
              retry_count: 0,
              last_error: '',
              updated_at: '2026-05-06T09:00:00Z',
            },
          ],
        },
      },
    });
  });
}

test('editor can generate a daily trading review from the reports page', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await page.getByTestId('nav-reports').click();

  await expect(page.getByTestId('reports-page')).toBeVisible();
  await expect(page.getByRole('heading', { name: '研究报表' })).toBeVisible();

  const reviewResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/reports/daily-review') && response.request().method() === 'POST'
  ));
  await page.getByTestId('daily-review-submit-button').click();
  expect((await reviewResponse).status()).toBe(200);

  await expect(page.getByRole('heading', { name: '每日交易复盘' })).toBeVisible();
  await expect(page.getByText('每日复盘已生成')).toBeVisible();
  await expect(page.getByTestId('daily-review-summary')).toContainText('账户权益');
  await expect(page.getByTestId('daily-review-message')).toContainText('交易账户');
});

test('admin can retry failed external push deliveries from the reports page', async ({ page }) => {
  await loginFresh(page);
  await mockReportsPageData(page);

  let retryRequests = 0;
  await page.route('**/api/v1/settings/external-push-deliveries/delivery-failed-1/retry', async (route) => {
    retryRequests += 1;
    await route.fulfill({
      json: {
        code: 0,
        data: { queued: true },
      },
    });
  });

  await page.getByTestId('nav-reports').click();

  const deliveriesSection = page.locator('section').filter({
    has: page.getByRole('heading', { name: 'External Push Deliveries' }),
  });
  await expect(deliveriesSection).toBeVisible();
  await expect(deliveriesSection).toContainText('Failed: 1, queued: 2, sent: 3.');
  await expect(deliveriesSection).toContainText('failed');
  await expect(deliveriesSection).toContainText('webhook:daily-review-webhook');
  await expect(deliveriesSection).toContainText('task-retry-1');
  await expect(deliveriesSection).toContainText('HTTP 500 from downstream');

  const retryButtons = deliveriesSection.getByRole('button', { name: 'Retry' });
  await expect(retryButtons).toHaveCount(2);
  await expect(retryButtons.first()).toBeEnabled();
  await expect(retryButtons.nth(1)).toBeDisabled();

  const retryResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/settings/external-push-deliveries/delivery-failed-1/retry')
      && response.request().method() === 'POST'
  ));
  await retryButtons.first().click();
  expect((await retryResponse).status()).toBe(200);
  expect(retryRequests).toBe(1);
  await expect(page.getByText('External push delivery retry queued.')).toBeVisible();
});

test('editor can view external push deliveries but retry is admin-only', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await mockReportsPageData(page);

  await page.getByTestId('nav-reports').click();

  const deliveriesSection = page.locator('section').filter({
    has: page.getByRole('heading', { name: 'External Push Deliveries' }),
  });
  const retryButtons = deliveriesSection.getByRole('button', { name: 'Retry' });
  await expect(deliveriesSection).toContainText('Failed: 1, queued: 2, sent: 3.');
  await expect(retryButtons).toHaveCount(2);
  await expect(retryButtons.first()).toBeDisabled();
  await expect(retryButtons.nth(1)).toBeDisabled();
});

test('viewer can read reports without loading write-only push audit endpoints', async ({ page }) => {
  await loginFresh(page, 'e2e_viewer', 'testpass');
  let deliveryCalls = 0;
  await page.route('**/api/v1/settings/external-push-deliveries?*', async (route) => {
    deliveryCalls += 1;
    await route.fulfill({
      status: 403,
      json: { code: 403, message: 'forbidden' },
    });
  });

  await page.getByTestId('nav-reports').click();

  await expect(page.getByTestId('reports-page')).toBeVisible();
  await expect(page.getByTestId('reports-readonly-warning')).toBeVisible();
  await expect(page.getByTestId('daily-review-submit-button')).toBeDisabled();
  expect(deliveryCalls).toBe(0);
});
