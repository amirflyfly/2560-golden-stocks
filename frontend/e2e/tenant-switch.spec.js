import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page);
}

test('租户切换会更新 localStorage、请求头和当前租户标记', async ({ page }) => {
  await loginFresh(page);
  await page.locator('.tenant-advanced summary').click();
  const tenantInput = page.getByTestId('tenant-switcher-input');
  await expect(tenantInput).toBeVisible();
  await expect(tenantInput).toHaveValue('1');

  const tenantTwoRequest = page.waitForRequest((request) => (
    request.url().includes('/api/v1/admin/tenants') && request.headers()['x-tenant-id'] === '2'
  ));

  await tenantInput.fill('2');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('tenant_id'))).toBe('2');
  await page.getByTestId('nav-admin').click();
  await tenantTwoRequest;

  await expect(page.getByTestId('admin-tenants-table')).toBeVisible();
  await expect(page.getByTestId('admin-tenant-row-tenant-two')).toContainText('active / 当前');
});
