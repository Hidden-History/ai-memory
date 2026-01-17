import { test as setup, expect } from '@playwright/test';

const authFile = 'tests/e2e/.auth/grafana.json';

/**
 * Authentication setup for Grafana
 * Logs in once and saves authentication state for all tests
 */
setup('authenticate to Grafana', async ({ page }) => {
  console.log('Navigating to Grafana login page...');
  await page.goto('http://localhost:23000/login');

  // Wait for login form to be visible
  await page.waitForSelector('input[name="user"]', { timeout: 10000 });

  console.log('Filling in credentials...');
  // Fill in username
  await page.fill('input[name="user"]', 'admin');

  // Fill in password
  await page.fill('input[name="password"]', 'admin');

  console.log('Submitting login form...');
  // Click login button
  await page.click('button[type="submit"]');

  // Wait for successful login - check for home page or skip button
  try {
    // Grafana may show a "skip" button for password change on first login
    const skipButton = page.locator('button:has-text("Skip")');
    if (await skipButton.isVisible({ timeout: 3000 })) {
      console.log('Clicking skip button for password change...');
      await skipButton.click();
    }
  } catch (e) {
    console.log('No skip button found, proceeding...');
  }

  // Verify we're logged in by checking for Grafana home elements
  await page.waitForURL(/.*\/\?orgId=\d+/, { timeout: 10000 });

  console.log('Login successful, verifying...');
  // Verify we can see the main navigation
  await expect(page.locator('[data-testid="data-testid Nav menu"]')).toBeVisible();

  console.log('Saving authentication state...');
  // Save authentication state
  await page.context().storageState({ path: authFile });
});
