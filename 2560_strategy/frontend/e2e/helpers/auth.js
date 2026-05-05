import { expect } from '@playwright/test';

export async function loginViaUi(page, username = 'admin', password = 'admin123') {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: '2560战法复盘系统' })).toBeVisible();
  await page.getByPlaceholder('请输入用户名').fill(username);
  await page.getByPlaceholder('请输入密码').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto('/stock-chart');
  await expect(page.getByRole('heading', { name: '2560 strategy' })).toBeVisible();
}

export async function logout(page) {
  await page.goto('/logout');
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible();
}
