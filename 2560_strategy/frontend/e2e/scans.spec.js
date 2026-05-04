import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('admin 可以创建扫描任务并看到数据质量字段', async ({ page }) => {
  await loginFresh(page);
  await page.getByTestId('nav-scans').click();
  await expect(page.getByRole('heading', { name: '策略扫描' })).toBeVisible();

  const scanResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/scans') && response.request().method() === 'POST'
  ));
  await page.getByTestId('create-scan-button').click();
  expect((await scanResponse).status()).toBe(202);

  const result = page.getByTestId('scan-result');
  await expect(result).toContainText('market_data');
  await expect(result).toContainText('actual_provider');
  await expect(result).toContainText('data_quality');
});

test('editor 可以创建扫描任务', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await page.getByTestId('nav-scans').click();
  await page.getByTestId('create-scan-button').click();
  await expect(page.getByTestId('scan-result')).toContainText('strategy_code');
});

test('viewer 创建扫描任务会展示权限不足', async ({ page }) => {
  await loginFresh(page, 'e2e_viewer', 'testpass');
  await page.getByTestId('nav-scans').click();
  await page.getByTestId('create-scan-button').click();
  await expect(page.getByTestId('scan-error')).toContainText('权限不足');
});
