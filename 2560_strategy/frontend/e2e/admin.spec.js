import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('admin 可以查看后台用户与租户表', async ({ page }) => {
  await loginFresh(page);
  await page.getByTestId('nav-admin').click();
  await expect(page.getByRole('heading', { name: '后台管理' })).toBeVisible();
  await expect(page.getByTestId('admin-users-table')).toContainText('admin');
  await expect(page.getByTestId('admin-tenants-table')).toContainText('默认租户');
  await expect(page.getByTestId('admin-tenant-row-default')).toContainText('当前');
});

test('admin 可以修改测试用户角色并在 UI 中反映', async ({ page }) => {
  await loginFresh(page);
  await page.getByTestId('nav-admin').click();
  const roleSelect = page.getByTestId('admin-user-role-e2e_viewer');
  await expect(roleSelect).toBeVisible();
  await roleSelect.selectOption('editor');
  await expect(roleSelect).toHaveValue('editor');
  await roleSelect.selectOption('viewer');
  await expect(roleSelect).toHaveValue('viewer');
});

test('editor 打开后台管理时展示权限错误', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await page.getByTestId('nav-admin').click();
  await expect(page.getByTestId('admin-error')).toContainText('权限不足');
});
