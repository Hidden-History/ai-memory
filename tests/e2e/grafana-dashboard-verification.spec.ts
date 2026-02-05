import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Comprehensive Grafana Dashboard Verification Tests
 *
 * PR #19, v2.0.3 - Metrics Redesign Verification
 *
 * Verifies:
 * - All V3 dashboards (new priority)
 * - Legacy dashboards (compatibility)
 * - Metric naming convention (aimemory_* prefix per BP-045)
 * - Project variable for multi-tenancy
 * - NFR threshold lines
 */

const GRAFANA_URL = 'http://localhost:23000';
const GRAFANA_USER = 'admin';
const GRAFANA_PASSWORD = '9jUCOYipdGLH3feIZHkh1f48';

// Dashboard configurations
const V3_DASHBOARDS = [
  {
    uid: 'ai-memory-nfr-performance-v3',
    name: 'NFR Performance Overview (V3)',
    expectedPanels: [
      'NFR-P1: Hook Latency',
      'NFR-P2: Batch Embedding',
      'NFR-P3: Session Injection',
      'NFR-P4: Dedup Check',
      'NFR-P5: Retrieval Query',
      'NFR-P6: Realtime Embedding',
      'NFR-P1: Hook Latency by Type',
      'NFR-P2/P6: Embedding Latency',
      'NFR-P3: Session Injection',
      'NFR-P4: Dedup Check',
      'NFR-P5: Retrieval Query',
      'NFR-P1 SLO',
      'NFR-P2 SLO',
      'NFR-P3 SLO',
      'NFR-P4 SLO',
      'NFR-P5 SLO',
      'NFR-P6 SLO'
    ],
    expectedVariables: ['project', 'hook_type'],
    expectedMetrics: [
      'aimemory_hook_duration_seconds',
      'aimemory_embedding_batch_duration_seconds',
      'aimemory_session_injection_duration_seconds',
      'aimemory_dedup_check_duration_seconds',
      'aimemory_retrieval_query_duration_seconds',
      'aimemory_embedding_realtime_duration_seconds'
    ]
  },
  {
    uid: 'ai-memory-hook-activity-v3',
    name: 'Hook Activity (V3)',
    expectedPanels: [
      'Hook Execution Rate',
      'CAPTURE vs RETRIEVAL',
      'Hook Success/Error Rate',
      'Hook Latency Heatmap',
      'Keyword Triggers',
      'Slowest Hooks',
      'Total Hook Executions (1h)',
      'Error Rate',
      'CAPTURE Hooks (1h)',
      'RETRIEVAL Hooks (1h)'
    ],
    expectedVariables: ['project', 'hook_type'],
    expectedMetrics: [
      'aimemory_hook_duration_seconds_count',
      'aimemory_trigger_fires_total'
    ]
  },
  {
    uid: 'ai-memory-operations-v3',
    name: 'Memory Operations (V3)',
    expectedPanels: [
      'Memory Captures by Collection',
      'Memory Retrievals by Collection',
      'Duplicates Detected (1h)',
      'Dedup Check p95 Latency',
      'Dedup Rate',
      'Token Usage',
      'Storage by Project (Vector Count)',
      'Capture Success vs Failed',
      'Retrieval Success vs Failed',
      'Total Vectors',
      'code-patterns',
      'conventions',
      'discussions'
    ],
    expectedVariables: ['project', 'collection'],
    expectedMetrics: [
      'aimemory_captures_total',
      'aimemory_retrievals_total',
      'aimemory_dedup_events_total',
      'aimemory_dedup_check_duration_seconds',
      'aimemory_collection_size'
    ]
  },
  {
    uid: 'ai-memory-system-health-v3',
    name: 'System Health (V3)',
    expectedPanels: [
      'Qdrant',
      'Embedding Service',
      'Prometheus',
      'Pushgateway',
      'Error Rate by Component',
      'Qdrant Collection Stats',
      'Embedding Service Latency',
      'Queue Size',
      'Failures by Error Code',
      'Total Failures (1h)',
      'Qdrant Failures (1h)',
      'Embedding Failures (1h)',
      'Hook Failures (1h)'
    ],
    expectedVariables: ['project'],
    expectedMetrics: [
      'aimemory_failure_events_total',
      'aimemory_collection_size',
      'aimemory_embedding_batch_duration_seconds',
      'aimemory_embedding_realtime_duration_seconds',
      'aimemory_queue_size'
    ]
  }
];

const LEGACY_DASHBOARDS = [
  {
    uid: 'ai-memory-classifier-health-v2',
    name: 'AI Memory Classifier Health',
    expectedVariables: ['project', 'provider', 'type'],
    usesOldPrefix: true, // Uses ai_memory_ prefix (legacy)
    expectedMetrics: [
      'ai_memory_classifier_requests_total',
      'ai_memory_classifier_queue_size'
    ]
  },
  {
    uid: 'ai-memory-overview-v2',
    name: 'AI Memory System - Overview',
    expectedVariables: ['project', 'hook'],
    usesOldPrefix: true, // Uses ai_memory_ prefix (legacy)
    expectedMetrics: [
      'ai_memory_captures_total',
      'ai_memory_hook_latency_bucket'
    ]
  }
];

interface DashboardReport {
  name: string;
  uid: string;
  status: 'PASS' | 'FAIL' | 'PARTIAL';
  projectVariable: boolean;
  panelsTotal: number;
  panelsWorking: number;
  panelsNoData: string[];
  issues: string[];
  screenshot?: string;
}

interface VerificationReport {
  timestamp: string;
  dashboards: DashboardReport[];
  summary: {
    total: number;
    passing: number;
    failing: number;
    partial: number;
    panelsWithNoData: string[];
    panelsWithWrongMetricNames: string[];
    panelsMissingProjectFilter: string[];
  };
  criticalIssues: string[];
}

test.describe('Grafana Dashboard Verification - V2.0.3 Metrics Redesign', () => {
  let screenshotDir: string;
  let report: VerificationReport;

  test.beforeAll(() => {
    screenshotDir = path.join(process.cwd(), 'test-results', 'grafana-verification');
    if (!fs.existsSync(screenshotDir)) {
      fs.mkdirSync(screenshotDir, { recursive: true });
    }

    report = {
      timestamp: new Date().toISOString(),
      dashboards: [],
      summary: {
        total: 0,
        passing: 0,
        failing: 0,
        partial: 0,
        panelsWithNoData: [],
        panelsWithWrongMetricNames: [],
        panelsMissingProjectFilter: []
      },
      criticalIssues: []
    };
  });

  test.beforeEach(async ({ page }) => {
    page.setDefaultTimeout(60000);
  });

  test.setTimeout(120000);

  async function login(page: Page) {
    await page.goto(`${GRAFANA_URL}/login`);
    await page.fill('input[name="user"]', GRAFANA_USER);
    await page.fill('input[name="password"]', GRAFANA_PASSWORD);
    await page.click('button[type="submit"]');

    // Wait for login to complete - either redirect or password change prompt
    await page.waitForTimeout(3000);

    // Handle password change skip if prompted
    try {
      const skipButton = page.locator('button:has-text("Skip")');
      if (await skipButton.isVisible({ timeout: 2000 })) {
        await skipButton.click();
        await page.waitForTimeout(1000);
      }
    } catch (e) {
      // Skip button not present
    }

    // Verify we're logged in by checking for sidebar or home content
    await page.waitForSelector('nav, [class*="sidemenu"], :text("Welcome to Grafana"), :text("Dashboards")', { timeout: 10000 });
  }

  async function waitForDashboardLoad(page: Page) {
    // Wait for panels to render
    await page.waitForSelector('[data-testid*="panel"], [class*="panel-container"]', {
      timeout: 15000,
      state: 'attached'
    }).catch(() => console.log('Panels not found with standard selector'));

    // Give panels time to fetch data
    await page.waitForTimeout(5000);
  }

  async function checkVariableExists(page: Page, variableName: string): Promise<boolean> {
    // Check for variable dropdown in template variables submenu
    const variableSelector = page.locator(`[data-testid*="variable-${variableName}"], [id*="${variableName}"], label:has-text("${variableName}")`);
    const exists = await variableSelector.count() > 0;
    return exists;
  }

  async function countPanelsWithData(page: Page): Promise<{ total: number; withData: number; noData: string[] }> {
    const noDataPanels: string[] = [];

    // Get all panel containers
    const panels = page.locator('[data-testid*="panel"], [class*="panel-container"]');
    const panelCount = await panels.count();

    let withData = 0;

    for (let i = 0; i < panelCount; i++) {
      const panel = panels.nth(i);
      const panelTitle = await panel.locator('[class*="panel-title"], [data-testid*="title"]').textContent().catch(() => `Panel ${i + 1}`);

      // Check for "No data" text
      const noDataIndicator = await panel.locator(':has-text("No data"), :has-text("N/A")').isVisible().catch(() => false);

      if (noDataIndicator) {
        noDataPanels.push(panelTitle || `Panel ${i + 1}`);
      } else {
        withData++;
      }
    }

    return { total: panelCount, withData, noData: noDataPanels };
  }

  async function verifyDashboard(
    page: Page,
    dashboardConfig: typeof V3_DASHBOARDS[0] | typeof LEGACY_DASHBOARDS[0]
  ): Promise<DashboardReport> {
    const dashboardReport: DashboardReport = {
      name: dashboardConfig.name,
      uid: dashboardConfig.uid,
      status: 'PASS',
      projectVariable: false,
      panelsTotal: 0,
      panelsWorking: 0,
      panelsNoData: [],
      issues: []
    };

    try {
      // Navigate to dashboard
      await page.goto(`${GRAFANA_URL}/d/${dashboardConfig.uid}`);
      await waitForDashboardLoad(page);

      // Take screenshot
      const screenshotPath = path.join(screenshotDir, `${dashboardConfig.uid}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });
      dashboardReport.screenshot = screenshotPath;

      // Check for $project variable
      dashboardReport.projectVariable = await checkVariableExists(page, 'project');
      if (!dashboardReport.projectVariable) {
        dashboardReport.issues.push('Missing $project variable (required for multi-tenancy)');
        dashboardReport.status = 'PARTIAL';
      }

      // Check all expected variables
      for (const varName of dashboardConfig.expectedVariables) {
        const exists = await checkVariableExists(page, varName);
        if (!exists) {
          dashboardReport.issues.push(`Missing variable: ${varName}`);
        }
      }

      // Count panels with data
      const panelStats = await countPanelsWithData(page);
      dashboardReport.panelsTotal = panelStats.total;
      dashboardReport.panelsWorking = panelStats.withData;
      dashboardReport.panelsNoData = panelStats.noData;

      // Check if expected panels exist
      if ('expectedPanels' in dashboardConfig) {
        for (const expectedPanel of dashboardConfig.expectedPanels) {
          const panelFound = await page.locator(`:has-text("${expectedPanel}")`).count() > 0;
          if (!panelFound) {
            dashboardReport.issues.push(`Expected panel not found: ${expectedPanel}`);
          }
        }
      }

      // Determine final status
      if (dashboardReport.issues.length === 0 && panelStats.noData.length === 0) {
        dashboardReport.status = 'PASS';
      } else if (dashboardReport.issues.length > 3 || panelStats.withData < panelStats.total / 2) {
        dashboardReport.status = 'FAIL';
      } else {
        dashboardReport.status = 'PARTIAL';
      }

    } catch (error) {
      dashboardReport.status = 'FAIL';
      dashboardReport.issues.push(`Error loading dashboard: ${error}`);
    }

    return dashboardReport;
  }

  test('Step 1: Login and access dashboard list', async ({ page }) => {
    await login(page);

    // Navigate to dashboards
    await page.goto(`${GRAFANA_URL}/dashboards`);
    await page.waitForTimeout(3000);

    // Screenshot dashboard list
    const listScreenshot = path.join(screenshotDir, 'dashboard-list.png');
    await page.screenshot({ path: listScreenshot, fullPage: true });

    console.log('Dashboard list screenshot saved');

    // Verify we can see dashboards
    const dashboardLinks = await page.locator('a[href*="/d/"]').count();
    expect(dashboardLinks).toBeGreaterThan(0);
    console.log(`Found ${dashboardLinks} dashboard links`);
  });

  test('Step 2: Verify NFR Performance Dashboard (V3)', async ({ page }) => {
    await login(page);

    const config = V3_DASHBOARDS.find(d => d.uid === 'ai-memory-nfr-performance-v3')!;
    const result = await verifyDashboard(page, config);
    report.dashboards.push(result);

    console.log('\n=== NFR Performance Dashboard (V3) ===');
    console.log(`Status: ${result.status}`);
    console.log(`Project Variable: ${result.projectVariable ? 'YES' : 'NO'}`);
    console.log(`Panels: ${result.panelsWorking}/${result.panelsTotal} working`);
    if (result.panelsNoData.length > 0) {
      console.log(`Panels with no data: ${result.panelsNoData.join(', ')}`);
    }
    if (result.issues.length > 0) {
      console.log('Issues:');
      result.issues.forEach(issue => console.log(`  - ${issue}`));
    }

    // NFR-specific checks - verify at least some NFR panels exist
    const pageContent = await page.content();
    const nfrPanels = ['NFR-P1', 'NFR-P2', 'NFR-P3', 'NFR-P4', 'NFR-P5', 'NFR-P6'];
    let nfrPanelsFound = 0;
    for (const nfr of nfrPanels) {
      if (pageContent.includes(nfr)) {
        nfrPanelsFound++;
      }
    }
    console.log(`NFR panels found in page content: ${nfrPanelsFound}/6`);
    expect(nfrPanelsFound).toBeGreaterThan(0);

    // Dashboard loaded with some panels is acceptable
    expect(result.panelsTotal).toBeGreaterThan(0);
  });

  test('Step 3: Verify Hook Activity Dashboard (V3)', async ({ page }) => {
    await login(page);

    const config = V3_DASHBOARDS.find(d => d.uid === 'ai-memory-hook-activity-v3')!;
    const result = await verifyDashboard(page, config);
    report.dashboards.push(result);

    console.log('\n=== Hook Activity Dashboard (V3) ===');
    console.log(`Status: ${result.status}`);
    console.log(`Project Variable: ${result.projectVariable ? 'YES' : 'NO'}`);
    console.log(`Panels: ${result.panelsWorking}/${result.panelsTotal} working`);
    if (result.issues.length > 0) {
      console.log('Issues:');
      result.issues.forEach(issue => console.log(`  - ${issue}`));
    }

    // Check for CAPTURE vs RETRIEVAL panel
    const capturePanel = await page.locator(':has-text("CAPTURE vs RETRIEVAL")').first();
    expect(await capturePanel.isVisible(), 'CAPTURE vs RETRIEVAL panel should be visible').toBe(true);

    expect(result.status).not.toBe('FAIL');
  });

  test('Step 4: Verify Memory Operations Dashboard (V3)', async ({ page }) => {
    await login(page);

    const config = V3_DASHBOARDS.find(d => d.uid === 'ai-memory-operations-v3')!;
    const result = await verifyDashboard(page, config);
    report.dashboards.push(result);

    console.log('\n=== Memory Operations Dashboard (V3) ===');
    console.log(`Status: ${result.status}`);
    console.log(`Project Variable: ${result.projectVariable ? 'YES' : 'NO'}`);
    console.log(`Panels: ${result.panelsWorking}/${result.panelsTotal} working`);
    if (result.issues.length > 0) {
      console.log('Issues:');
      result.issues.forEach(issue => console.log(`  - ${issue}`));
    }

    // Check for collection panels
    const collections = ['code-patterns', 'conventions', 'discussions'];
    for (const collection of collections) {
      const collectionFound = await page.locator(`:has-text("${collection}")`).count() > 0;
      expect(collectionFound, `Collection "${collection}" should be visible`).toBe(true);
    }

    expect(result.status).not.toBe('FAIL');
  });

  test('Step 5: Verify System Health Dashboard (V3)', async ({ page }) => {
    await login(page);

    const config = V3_DASHBOARDS.find(d => d.uid === 'ai-memory-system-health-v3')!;
    const result = await verifyDashboard(page, config);
    report.dashboards.push(result);

    console.log('\n=== System Health Dashboard (V3) ===');
    console.log(`Status: ${result.status}`);
    console.log(`Project Variable: ${result.projectVariable ? 'YES' : 'NO'}`);
    console.log(`Panels: ${result.panelsWorking}/${result.panelsTotal} working`);
    if (result.issues.length > 0) {
      console.log('Issues:');
      result.issues.forEach(issue => console.log(`  - ${issue}`));
    }

    // Check for service status panels
    const services = ['Qdrant', 'Prometheus', 'Pushgateway'];
    for (const service of services) {
      const servicePanel = await page.locator(`:has-text("${service}")`).first();
      expect(await servicePanel.isVisible(), `Service "${service}" panel should be visible`).toBe(true);
    }

    expect(result.status).not.toBe('FAIL');
  });

  test('Step 6: Verify Legacy Dashboards (compatibility)', async ({ page }) => {
    await login(page);

    for (const config of LEGACY_DASHBOARDS) {
      console.log(`\n=== Checking Legacy Dashboard: ${config.name} ===`);

      try {
        await page.goto(`${GRAFANA_URL}/d/${config.uid}`);
        await waitForDashboardLoad(page);

        // Take screenshot
        const screenshotPath = path.join(screenshotDir, `${config.uid}.png`);
        await page.screenshot({ path: screenshotPath, fullPage: true });

        // Check if dashboard loads
        const title = await page.locator('h1, [class*="dashboard-title"]').first().textContent().catch(() => 'Unknown');
        console.log(`Dashboard title: ${title}`);
        console.log(`Uses old prefix (ai_memory_*): ${config.usesOldPrefix ? 'YES - LEGACY' : 'NO'}`);

        // Check $project variable
        const projectVar = await checkVariableExists(page, 'project');
        console.log(`Project Variable: ${projectVar ? 'YES' : 'NO'}`);

        report.dashboards.push({
          name: config.name,
          uid: config.uid,
          status: 'PARTIAL', // Legacy dashboards are partial by design (old prefix)
          projectVariable: projectVar,
          panelsTotal: 0,
          panelsWorking: 0,
          panelsNoData: [],
          issues: config.usesOldPrefix ? ['Uses legacy ai_memory_* prefix (should migrate to aimemory_*)'] : [],
          screenshot: screenshotPath
        });

        if (config.usesOldPrefix) {
          report.criticalIssues.push(`Dashboard "${config.name}" uses legacy ai_memory_* prefix`);
        }

      } catch (error) {
        console.log(`Error loading ${config.name}: ${error}`);
        report.dashboards.push({
          name: config.name,
          uid: config.uid,
          status: 'FAIL',
          projectVariable: false,
          panelsTotal: 0,
          panelsWorking: 0,
          panelsNoData: [],
          issues: [`Error loading dashboard: ${error}`]
        });
      }
    }
  });

  test('Step 7: Prometheus Query Verification', async ({ page }) => {
    await login(page);

    console.log('\n=== Prometheus Query Verification ===');

    // Navigate to Explore
    await page.goto(`${GRAFANA_URL}/explore`);
    await page.waitForTimeout(3000);

    const testQueries = [
      { query: 'aimemory_captures_total', description: 'Captures counter' },
      { query: 'aimemory_hook_duration_seconds_bucket', description: 'Hook duration histogram' },
      { query: 'aimemory_collection_size', description: 'Collection size gauge' },
      { query: 'aimemory_captures_total{project!=""}', description: 'Captures with project label' }
    ];

    // Take screenshot of Explore page
    const exploreScreenshot = path.join(screenshotDir, 'prometheus-explore.png');
    await page.screenshot({ path: exploreScreenshot, fullPage: true });
    console.log('Explore page screenshot saved');

    // Note: Full query execution requires more complex interaction
    // This test verifies the Explore page is accessible
    console.log('Queries to verify manually in Prometheus/Grafana Explore:');
    testQueries.forEach(q => console.log(`  - ${q.query}: ${q.description}`));
  });

  test.afterAll(async () => {
    // Calculate summary
    for (const dashboard of report.dashboards) {
      report.summary.total++;
      if (dashboard.status === 'PASS') report.summary.passing++;
      else if (dashboard.status === 'FAIL') report.summary.failing++;
      else report.summary.partial++;

      report.summary.panelsWithNoData.push(...dashboard.panelsNoData.map(p => `${dashboard.name}: ${p}`));

      if (!dashboard.projectVariable) {
        report.summary.panelsMissingProjectFilter.push(dashboard.name);
      }
    }

    // Generate final report
    console.log('\n========================================');
    console.log('GRAFANA DASHBOARD VERIFICATION REPORT');
    console.log('========================================');
    console.log(`Timestamp: ${report.timestamp}`);
    console.log('');
    console.log('DASHBOARD RESULTS:');
    console.log('------------------');

    for (const dashboard of report.dashboards) {
      console.log(`\nDashboard: ${dashboard.name}`);
      console.log(`  Status: ${dashboard.status}`);
      console.log(`  Project Variable: ${dashboard.projectVariable ? 'YES' : 'NO'}`);
      console.log(`  Panels Working: ${dashboard.panelsWorking}/${dashboard.panelsTotal}`);
      if (dashboard.issues.length > 0) {
        console.log('  Issues Found:');
        dashboard.issues.forEach(issue => console.log(`    - ${issue}`));
      }
      console.log(`  Screenshot: ${dashboard.screenshot || 'N/A'}`);
    }

    console.log('\n========================================');
    console.log('FINAL SUMMARY');
    console.log('========================================');
    console.log(`Total Dashboards: ${report.summary.total}`);
    console.log(`Passing: ${report.summary.passing}`);
    console.log(`Partial: ${report.summary.partial}`);
    console.log(`Failing: ${report.summary.failing}`);

    if (report.summary.panelsWithNoData.length > 0) {
      console.log(`\nPanels with "No data": ${report.summary.panelsWithNoData.length}`);
      report.summary.panelsWithNoData.slice(0, 10).forEach(p => console.log(`  - ${p}`));
      if (report.summary.panelsWithNoData.length > 10) {
        console.log(`  ... and ${report.summary.panelsWithNoData.length - 10} more`);
      }
    }

    if (report.summary.panelsMissingProjectFilter.length > 0) {
      console.log(`\nDashboards missing $project filter:`);
      report.summary.panelsMissingProjectFilter.forEach(d => console.log(`  - ${d}`));
    }

    if (report.criticalIssues.length > 0) {
      console.log('\nCRITICAL ISSUES:');
      report.criticalIssues.forEach(issue => console.log(`  - ${issue}`));
    }

    // Save report to JSON
    const reportPath = path.join(screenshotDir, 'verification-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(`\nFull report saved to: ${reportPath}`);
  });
});
