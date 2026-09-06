import { expect, test } from '@playwright/test';

test('登录页可在 Mock 模式渲染', async ({ page }) => {
  await page.goto('/login?mock=1');

  await expect(page.getByRole('region', { name: '账号认证' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '登录智课未来' })).toBeVisible();
  await expect(page.getByLabel('邮箱')).toBeVisible();
  await expect(page.locator('#auth-password')).toBeVisible();
  await expect(page.getByRole('button', { name: '登录工作台' })).toBeVisible();
});
