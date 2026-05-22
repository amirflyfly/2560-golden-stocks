import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('editor can review paper trading closed-loop workbench', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await page.getByTestId('nav-trading').click();

  await expect(page.getByTestId('paper-trading-page')).toBeVisible();
  await expect(page.getByTestId('paper-account-risk')).toBeVisible();
  await expect(page.getByTestId('paper-account-risk')).toContainText('账户权益');
  await expect(page.getByTestId('paper-account-risk')).toContainText('链路完整率');
  await expect(page.getByTestId('paper-loop-panel')).toBeVisible();
  await expect(page.getByTestId('paper-loop-panel')).toContainText('今日闭环驾驶舱');
  await expect(page.getByTestId('paper-loop-flow')).toBeVisible();
  await expect(page.getByTestId('paper-action-strip')).toBeVisible();
  await expect(page.getByTestId('paper-action-strip')).toContainText('同步持仓行情');
  await expect(page.getByTestId('paper-action-strip')).toContainText('检查止盈止损');
  await expect(page.getByTestId('paper-action-strip')).toContainText('查看明细证据');
  await expect(page.getByTestId('position-freshness-panel')).toBeVisible();
  await expect(page.getByTestId('position-freshness-panel')).toContainText('当前持仓盯盘');
  await expect(page.getByTestId('paper-trade-records')).toBeVisible();
  await expect(page.getByTestId('paper-trade-records')).toContainText('最近交易流水');
  await expect(page.getByTestId('paper-attribution-panel')).toBeVisible();
  await expect(page.getByTestId('paper-attribution-panel')).toContainText('复盘归因');

  const evidenceSection = page.locator('#paper-evidence-section');
  await expect(evidenceSection).toBeVisible();
  await evidenceSection.locator('summary').click();
  await expect(page.getByTestId('paper-positions-table')).toBeVisible();
  await expect(page.getByTestId('paper-signals-table')).toBeVisible();
  await expect(page.getByTestId('paper-links-table')).toBeVisible();
  await expect(page.getByTestId('paper-orders-table')).toBeVisible();
  await expect(page.getByTestId('paper-fills-table')).toBeVisible();

  await page.route('**/api/v1/trading/paper/complete-loop', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'ok',
        data: {
          schema_version: 'paper-complete-loop/v1',
          status: 'completed',
          strategy_summary: { executed: 1, matched_count: 2, buy_orders: 1, buy_skipped: 0, buy_blocked: 0 },
          strategy_runs: [
            {
              strategy_id: 1,
              strategy_code: '2560',
              strategy_name: '2560',
              status: 'completed',
              summary: { matched_count: 2, buy_orders: 1, buy_skipped: 0, buy_blocked: 0 },
            },
          ],
          position_monitor: {
            status: 'completed',
            symbol_count: 1,
            position_count: 1,
            snapshot_sync: { snapshot_count: 1, persisted_snapshots: 1, source: 'e2e' },
            accounts: [{ account_id: 1, mark_to_market: { updated: 1 }, exits: { orders: 0 } }],
            exit_summary: { orders: 0, skipped: 1, blocked: 0 },
          },
          updated_at: '2026-05-12T10:00:00',
          source: 'e2e',
        },
      }),
    });
  });
  page.on('dialog', (dialog) => dialog.accept());
  const loopResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/complete-loop') && response.request().method() === 'POST'
  ));
  await page.getByTestId('paper-run-loop-button').click();
  expect((await loopResponse).status()).toBe(200);
  await expect(page.getByTestId('paper-loop-panel')).toContainText(/策略运行|模拟买入|行情同步|闭环时间/);
  await expect(page.getByTestId('paper-loop-flow').locator('.paper-loop-node').filter({ hasText: '策略选标的' })).toContainText('2');
  await expect(page.getByTestId('paper-loop-flow').locator('.paper-loop-node').filter({ hasText: '模拟买入' })).toContainText('1');
  await expect(page.getByTestId('paper-loop-flow').locator('.paper-loop-node').filter({ hasText: '行情/K线同步' })).toContainText('1');
  await expect(page.getByTestId('paper-loop-delta')).toBeVisible();
  await expect(page.getByTestId('paper-loop-runs')).toContainText('2560');
  await expect(page.getByTestId('paper-loop-evidence')).toContainText(/买单|成交|持仓|复盘链路/);

  const evaluateResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/evaluate-exits') && response.request().method() === 'POST'
  ));
  await page.getByTestId('paper-action-strip').getByRole('button', { name: '检查止盈止损' }).click();
  expect((await evaluateResponse).status()).toBe(200);

  await expect(page.getByTestId('paper-orders-table')).toBeVisible();
  await expect(page.getByTestId('paper-signals-table')).toBeVisible();
  await expect(page.getByTestId('paper-trade-records')).toContainText(/最近交易流水|暂无交易流水/);
  await expect(page.getByTestId('paper-attribution-panel')).toContainText(/复盘归因|暂无复盘归因记录/);
});
