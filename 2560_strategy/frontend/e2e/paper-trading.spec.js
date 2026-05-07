import { expect, test } from '@playwright/test';
import { loginViaUi } from './helpers/auth.js';

async function loginFresh(page, username = 'admin', password = 'admin123') {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await loginViaUi(page, username, password);
}

test('editor can review paper trading state and trigger exit evaluation', async ({ page }) => {
  await loginFresh(page, 'e2e_editor', 'testpass');
  await page.getByTestId('nav-trading').click();

  await expect(page.getByTestId('paper-trading-page')).toBeVisible();
  await expect(page.getByTestId('paper-positions-table')).toBeVisible();
  await expect(page.getByTestId('paper-signals-table')).toBeVisible();
  await expect(page.getByTestId('paper-orders-table')).toBeVisible();
  await expect(page.getByTestId('paper-fills-table')).toBeVisible();

  const evaluateResponse = page.waitForResponse((response) => (
    response.url().includes('/api/v1/trading/paper/evaluate-exits') && response.request().method() === 'POST'
  ));
  await page.getByTestId('paper-evaluate-exits-button').click();
  expect((await evaluateResponse).status()).toBe(200);

  await expect(page.getByTestId('paper-orders-table')).toBeVisible();
  await expect(page.getByTestId('paper-signals-table')).toBeVisible();
});
