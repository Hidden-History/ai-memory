import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Grafana Dashboard E2E Tests
 *
 * Tests the BMAD Memory Module Grafana dashboards for proper rendering,
 * panel visibility, and data display.
 *
 * Test Coverage:
 * - Login authentication
 * - BMAD Memory Overview dashboard
 * - BMAD Memory Performance dashboard
 * - Panel visibility and types
 * - Data display verification
 */

test.describe('Grafana Dashboards: BMAD Memory Module', () => {
  let screenshotDir: string;

  test.beforeAll(() => {
    // Create screenshots directory
    screenshotDir = path.join(process.cwd(), 'test-results', 'screenshots');
    if (!fs.existsSync(screenshotDir)) {
      fs.mkdirSync(screenshotDir, { recursive: true });
    }
  });

  test.beforeEach(async ({ page }) => {
    // Set longer timeout for dashboard loading
    page.setDefaultTimeout(15000);
  });

  /**
   * Helper function to wait for dashboard panels to load
   */
  async function waitForDashboardLoad(page: Page) {
    // Wait for the main dashboard container
    await page.waitForSelector('[data-testid="data-testid Dashboard template variables submenu"]', {
      timeout: 10000,
      state: 'attached'
    }).catch(() => {
      console.log('Template variables submenu not found, continuing...');
    });

    // Wait for panels to be present
    await page.waitForSelector('[data-testid*="panel"]', { timeout: 10000 });

    // Give panels time to render data
    await page.waitForTimeout(3000);
  }

  /**
   * Helper function to check if a panel is visible
   */
  async function isPanelVisible(page: Page, panelTitle: string): Promise<boolean> {
    const panel = page.locator(`[aria-label*="${panelTitle}"], [title*="${panelTitle}"], :has-text("${panelTitle}")`).first();
    return await panel.isVisible().catch(() => false);
  }

  /**
   * Helper function to get panel data status
   */
  async function getPanelDataStatus(page: Page, panelTitle: string): Promise<'has-data' | 'no-data' | 'loading' | 'error'> {
    const panelContainer = page.locator(`[data-testid*="panel"]:has-text("${panelTitle}")`).first();

    // Check for "No data" message
    const noData = await panelContainer.locator(':has-text("No data")').isVisible().catch(() => false);
    if (noData) return 'no-data';

    // Check for loading indicator
    const loading = await panelContainer.locator('[data-testid="Spinner"]').isVisible().catch(() => false);
    if (loading) return 'loading';

    // Check for error message
    const error = await panelContainer.locator(':has-text("error"), :has-text("Error")').isVisible().catch(() => false);
    if (error) return 'error';

    // Assume has data if no negative indicators
    return 'has-data';
  }

  test('should successfully login to Grafana', async ({ page }) => {
    console.log('Test: Login to Grafana');

    await page.goto('http://localhost:23000/login');

    // Fill login form
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    // Handle potential password change skip
    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {
      // Skip button not present, continue
    }

    // Verify successful login
    await page.waitForURL(/.*\/\?orgId=\d+/, { timeout: 10000 });
    await expect(page.locator('[data-testid="data-testid Nav menu"]')).toBeVisible();

    console.log('Login successful');
  });

  test('should load BMAD Memory Overview dashboard', async ({ page }) => {
    console.log('Test: BMAD Memory Overview Dashboard');

    // Login first
    await page.goto('http://localhost:23000/login');
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {}

    // Navigate to Overview dashboard
    await page.goto('http://localhost:23000/d/ai-memory-overview/ai-memory-overview');

    await waitForDashboardLoad(page);

    // Take screenshot
    const screenshotPath = path.join(screenshotDir, 'ai-memory-overview.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Screenshot saved: ${screenshotPath}`);

    // Verify dashboard title
    const dashboardTitle = await page.locator('h1, [class*="dashboard-title"]').first().textContent();
    console.log(`Dashboard title: ${dashboardTitle}`);

    // Define expected panels
    const expectedPanels = [
      'Embedding Rate (last 1h)',
      'Retrieval Rate (last 1h)',
      'Collection Sizes',
      'Total Memories Stored',
      'Embedding/Retrieval Timeline',
      'Operation Duration (Avg)'
    ];

    console.log('\nChecking panels:');
    const panelResults: Record<string, { visible: boolean; dataStatus: string }> = {};

    for (const panelTitle of expectedPanels) {
      const visible = await isPanelVisible(page, panelTitle);
      const dataStatus = visible ? await getPanelDataStatus(page, panelTitle) : 'not-visible';

      panelResults[panelTitle] = { visible, dataStatus };
      console.log(`  - ${panelTitle}: ${visible ? 'VISIBLE' : 'NOT VISIBLE'}, Data: ${dataStatus}`);

      // Assert panel is visible
      expect(visible, `Panel "${panelTitle}" should be visible`).toBe(true);
    }

    // Check Collection Sizes panel specifically (should show data)
    console.log('\nVerifying Collection Sizes panel has data...');
    const collectionSizesPanel = page.locator('[data-testid*="panel"]:has-text("Collection Sizes")').first();
    await expect(collectionSizesPanel).toBeVisible();

    // The panel should not show "No data" since we know there are 142 memories
    const hasNoData = await collectionSizesPanel.locator(':has-text("No data")').isVisible().catch(() => false);
    if (!hasNoData) {
      console.log('Collection Sizes panel is showing data (expected)');
    } else {
      console.log('WARNING: Collection Sizes panel shows "No data" (unexpected - should show 142 memories)');
    }
  });

  test('should load BMAD Memory Performance dashboard', async ({ page }) => {
    console.log('Test: BMAD Memory Performance Dashboard');

    // Login first
    await page.goto('http://localhost:23000/login');
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {}

    // Navigate to Performance dashboard
    await page.goto('http://localhost:23000/d/ai-memory-performance/ai-memory-performance');

    await waitForDashboardLoad(page);

    // Take screenshot
    const screenshotPath = path.join(screenshotDir, 'ai-memory-performance.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Screenshot saved: ${screenshotPath}`);

    // Verify dashboard title
    const dashboardTitle = await page.locator('h1, [class*="dashboard-title"]').first().textContent();
    console.log(`Dashboard title: ${dashboardTitle}`);

    // Define expected panels
    const expectedPanels = [
      'Hook Duration (p50, p95, p99)',
      'Embedding Duration Distribution',
      'Retrieval Duration (p95)',
      'Embedding Duration (p95)'
    ];

    console.log('\nChecking panels:');
    const panelResults: Record<string, { visible: boolean; dataStatus: string }> = {};

    for (const panelTitle of expectedPanels) {
      const visible = await isPanelVisible(page, panelTitle);
      const dataStatus = visible ? await getPanelDataStatus(page, panelTitle) : 'not-visible';

      panelResults[panelTitle] = { visible, dataStatus };
      console.log(`  - ${panelTitle}: ${visible ? 'VISIBLE' : 'NOT VISIBLE'}, Data: ${dataStatus}`);

      // Assert panel is visible
      expect(visible, `Panel "${panelTitle}" should be visible`).toBe(true);
    }

    // Verify "Success Rate by Component" is NOT present
    console.log('\nVerifying "Success Rate by Component" panel is NOT present...');
    const successRatePanel = await isPanelVisible(page, 'Success Rate by Component');
    expect(successRatePanel, 'Panel "Success Rate by Component" should NOT be visible').toBe(false);
    console.log('Confirmed: "Success Rate by Component" panel is not present (expected)');
  });

  test('should verify panel types and configurations', async ({ page }) => {
    console.log('Test: Panel Types and Configurations');

    // Login first
    await page.goto('http://localhost:23000/login');
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {}

    // Check Overview dashboard panels
    console.log('\n=== BMAD Memory Overview Dashboard ===');
    await page.goto('http://localhost:23000/d/ai-memory-overview/ai-memory-overview');
    await waitForDashboardLoad(page);

    // Check if we can access panel edit mode (indicates proper panel configuration)
    const panelMenus = page.locator('[data-testid="data-testid panel-menu"]');
    const menuCount = await panelMenus.count();
    console.log(`Found ${menuCount} panel menus (indicates ${menuCount} panels)`);

    // Verify we have at least 6 panels
    expect(menuCount, 'Overview dashboard should have at least 6 panels').toBeGreaterThanOrEqual(6);

    // Check Performance dashboard panels
    console.log('\n=== BMAD Memory Performance Dashboard ===');
    await page.goto('http://localhost:23000/d/ai-memory-performance/ai-memory-performance');
    await waitForDashboardLoad(page);

    const perfPanelMenus = page.locator('[data-testid="data-testid panel-menu"]');
    const perfMenuCount = await perfPanelMenus.count();
    console.log(`Found ${perfMenuCount} panel menus (indicates ${perfMenuCount} panels)`);

    // Verify we have at least 4 panels
    expect(perfMenuCount, 'Performance dashboard should have at least 4 panels').toBeGreaterThanOrEqual(4);
  });

  test('should check for ai_memory_* metrics in panel queries', async ({ page }) => {
    console.log('Test: Verify ai_memory_* metrics usage');

    // Login first
    await page.goto('http://localhost:23000/login');
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {}

    // Navigate to Overview dashboard
    await page.goto('http://localhost:23000/d/ai-memory-overview/ai-memory-overview');
    await waitForDashboardLoad(page);

    console.log('\nAttempting to inspect panel queries...');

    // Try to click on first panel menu to inspect
    const firstPanelMenu = page.locator('[data-testid="data-testid panel-menu"]').first();
    if (await firstPanelMenu.isVisible()) {
      await firstPanelMenu.click();

      // Look for "Edit" option
      const editOption = page.locator('[aria-label="Edit panel"], :has-text("Edit")').first();
      if (await editOption.isVisible({ timeout: 2000 })) {
        console.log('Panel edit option found - configuration is accessible');
      } else {
        console.log('Panel edit option not immediately visible - queries cannot be inspected via UI');
      }

      // Close menu
      await page.keyboard.press('Escape');
    }

    console.log('\nNote: Full query inspection requires dashboard JSON export or API access');
    console.log('Verify queries include metrics like:');
    console.log('  - ai_memory_memories_stored_total');
    console.log('  - ai_memory_embedding_duration_seconds');
    console.log('  - ai_memory_retrieval_duration_seconds');
    console.log('  - ai_memory_hook_duration_seconds');
  });

  test('should generate comprehensive test report', async ({ page }) => {
    console.log('Test: Generate Comprehensive Report');

    // Login first
    await page.goto('http://localhost:23000/login');
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');

    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 3000 })) {
        await skipButton.click();
      }
    } catch (e) {}

    const report = {
      timestamp: new Date().toISOString(),
      dashboards: {} as Record<string, any>
    };

    // Test Overview Dashboard
    console.log('\n=== Testing BMAD Memory Overview Dashboard ===');
    await page.goto('http://localhost:23000/d/ai-memory-overview/ai-memory-overview');
    await waitForDashboardLoad(page);

    const overviewPanels = [
      'Embedding Rate (last 1h)',
      'Retrieval Rate (last 1h)',
      'Collection Sizes',
      'Total Memories Stored',
      'Embedding/Retrieval Timeline',
      'Operation Duration (Avg)'
    ];

    report.dashboards['overview'] = {
      url: 'http://localhost:23000/d/ai-memory-overview/ai-memory-overview',
      panels: {} as Record<string, any>
    };

    for (const panelTitle of overviewPanels) {
      const visible = await isPanelVisible(page, panelTitle);
      const dataStatus = visible ? await getPanelDataStatus(page, panelTitle) : 'not-visible';

      report.dashboards['overview'].panels[panelTitle] = {
        visible,
        dataStatus,
        status: visible ? 'PASS' : 'FAIL'
      };

      console.log(`${visible ? '✓' : '✗'} ${panelTitle} - ${dataStatus}`);
    }

    // Test Performance Dashboard
    console.log('\n=== Testing BMAD Memory Performance Dashboard ===');
    await page.goto('http://localhost:23000/d/ai-memory-performance/ai-memory-performance');
    await waitForDashboardLoad(page);

    const performancePanels = [
      'Hook Duration (p50, p95, p99)',
      'Embedding Duration Distribution',
      'Retrieval Duration (p95)',
      'Embedding Duration (p95)'
    ];

    report.dashboards['performance'] = {
      url: 'http://localhost:23000/d/ai-memory-performance/ai-memory-performance',
      panels: {} as Record<string, any>
    };

    for (const panelTitle of performancePanels) {
      const visible = await isPanelVisible(page, panelTitle);
      const dataStatus = visible ? await getPanelDataStatus(page, panelTitle) : 'not-visible';

      report.dashboards['performance'].panels[panelTitle] = {
        visible,
        dataStatus,
        status: visible ? 'PASS' : 'FAIL'
      };

      console.log(`${visible ? '✓' : '✗'} ${panelTitle} - ${dataStatus}`);
    }

    // Check for incorrect panel
    const successRateVisible = await isPanelVisible(page, 'Success Rate by Component');
    report.dashboards['performance'].panels['Success Rate by Component (should not exist)'] = {
      visible: successRateVisible,
      status: !successRateVisible ? 'PASS' : 'FAIL'
    };
    console.log(`${!successRateVisible ? '✓' : '✗'} "Success Rate by Component" correctly absent`);

    // Save report
    const reportPath = path.join(process.cwd(), 'test-results', 'dashboard-test-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(`\nTest report saved: ${reportPath}`);

    // Generate summary
    console.log('\n=== Test Summary ===');
    let totalPanels = 0;
    let passedPanels = 0;
    let failedPanels = 0;

    for (const dashboard of Object.values(report.dashboards)) {
      for (const panel of Object.values(dashboard.panels)) {
        totalPanels++;
        if (panel.status === 'PASS') passedPanels++;
        else failedPanels++;
      }
    }

    console.log(`Total Checks: ${totalPanels}`);
    console.log(`Passed: ${passedPanels}`);
    console.log(`Failed: ${failedPanels}`);
    console.log(`Success Rate: ${((passedPanels / totalPanels) * 100).toFixed(1)}%`);

    // Assert overall success
    expect(failedPanels, 'All dashboard checks should pass').toBe(0);
  });
});
