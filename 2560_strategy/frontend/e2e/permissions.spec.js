import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';
import { apiRequest } from './helpers/api.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('未登录 API 请求返回 401', async ({ page }) => {
  await page.context().clearCookies();
  const response = await page.request.get('/api/v1/strategies', {
    headers: { 'X-Tenant-ID': '1' },
  });
  expect(response.status()).toBe(401);
});

test('viewer 通过 API 提交扫描返回 403', async ({ page }) => {
  await loginFresh(page, 'e2e_viewer', 'testpass');
  const response = await apiRequest(page, '/api/v1/scans', {
    method: 'POST',
    body: { strategy_code: '2560', params: {} },
  });
  expect(response.status()).toBe(403);
  expect((await response.json()).message).toBe('权限不足');
});

test('未绑定租户访问会展示用户未绑定该租户', async ({ page }) => {
  await loginFresh(page, 'e2e_unbound', 'testpass');
  await page.getByTestId('tenant-switcher-input').fill('2');
  await page.getByTestId('nav-scans').click();
  await page.getByTestId('create-scan-button').click();
  await expect(page.getByTestId('scan-error')).toContainText('用户未绑定该租户');
});

test('停用租户访问会展示租户已停用', async ({ page }) => {
  await loginFresh(page);
  await page.getByTestId('tenant-switcher-input').fill('3');
  await page.getByTestId('nav-admin').click();
  await expect(page.getByTestId('admin-error')).toContainText('租户已停用');
});
