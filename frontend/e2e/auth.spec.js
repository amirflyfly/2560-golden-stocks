import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function clearSession(page) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
}

test('未登录访问首页会跳转到登录页', async ({ page }) => {
  await clearSession(page);
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible();
});

test('admin 可以登录且刷新后会话保持', async ({ page }) => {
  await clearSession(page);
  await loginViaUi(page);
  await expect(page.getByTestId('nav-dashboard')).toHaveClass(/active/);
  await page.goto('/stock-chart');
  await expect(page.getByTestId('nav-scans')).toBeVisible();
});

test('错误密码会显示登录失败', async ({ page }) => {
  await clearSession(page);
  await page.getByPlaceholder('请输入用户名').fill('admin');
  await page.getByPlaceholder('请输入密码').fill('wrong-password');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('账号或密码错误')).toBeVisible();
});
