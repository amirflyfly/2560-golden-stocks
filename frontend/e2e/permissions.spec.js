import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';
import { apiRequest } from './helpers/api.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

async function openTenantInput(page) {
  await page.locator('.tenant-advanced summary').click();
  const tenantInput = page.getByTestId('tenant-switcher-input');
  await expect(tenantInput).toBeVisible();
  return tenantInput;
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
  const tenantInput = await openTenantInput(page);
  await tenantInput.fill('2');
  await expect(page.getByText('用户未绑定该租户')).toBeVisible();
});

test('停用租户访问会展示租户已停用', async ({ page }) => {
  await loginFresh(page);
  const tenantInput = await openTenantInput(page);
  await tenantInput.fill('3');
  await expect(page.getByText('租户已停用')).toBeVisible();
});
