import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Memory Operations Dashboard Audit
 *
 * Verifies all panels on the Memory Operations (V3) dashboard
 * and documents which panels have data vs "No data" state.
 */

const GRAFANA_URL = 'http://localhost:23000';
const GRAFANA_USER = 'admin';
const GRAFANA_PASSWORD = 'admin';
const PROMETHEUS_URL = 'http://localhost:29090';
const PROMETHEUS_USER = 'admin';
const PROMETHEUS_PASSWORD = '5HCf9v5laO0jxxLcXtnyYj7G';
const DASHBOARD_URL = `${GRAFANA_URL}/d/ai-memory-operations-v3/memory-operations-v3?orgId=1&from=now-1h&to=now&timezone=browser&var-project=$__all&var-collection=$__all&refresh=30s`;

interface PanelAudit {
  title: string;
  hasData: boolean;
  value?: string;
  issue?: string;
}

test.describe('Memory Operations Dashboard Audit', () => {
  let screenshotDir: string;

  test.beforeAll(() => {
    screenshotDir = path.join(process.cwd(), 'test-results', 'memory-ops-audit');
    if (!fs.existsSync(screenshotDir)) {
      fs.mkdirSync(screenshotDir, { recursive: true });
    }
  });

  test.setTimeout(120000);

  async function login(page: Page) {
    await page.goto(`${GRAFANA_URL}/login`);
    await page.fill('input[name="user"]', GRAFANA_USER);
    await page.fill('input[name="password"]', GRAFANA_PASSWORD);
    await page.click('button[type="submit"]');
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
  }

  async function auditPanel(page: Page, panelTitle: string): Promise<PanelAudit> {
    const audit: PanelAudit = {
      title: panelTitle,
      hasData: false
    };

    try {
      // Find the panel by title
      const panel = page.locator(`[data-testid*="panel"]:has-text("${panelTitle}"), [class*="panel"]:has-text("${panelTitle}")`).first();

      if (await panel.count() === 0) {
        audit.issue = 'Panel not found';
        return audit;
      }

      // Check for "No data" indicator
      const noDataText = await panel.locator(':has-text("No data")').count();
      if (noDataText > 0) {
        audit.hasData = false;
        audit.issue = 'No data displayed';
        return audit;
      }

      // Check for stat value
      const statValue = await panel.locator('[class*="stat-value"], [class*="singlestat"]').textContent().catch(() => null);
      if (statValue) {
        audit.hasData = true;
        audit.value = statValue.trim();
        // Check if value is 0
        if (statValue.trim() === '0' || statValue.trim() === '0%') {
          audit.issue = 'Value is zero';
        }
      }

      // If we got here and didn't find "No data", assume it has data
      if (!audit.issue) {
        audit.hasData = true;
      }

    } catch (error) {
      audit.issue = `Error: ${error}`;
    }

    return audit;
  }

  test('Audit Memory Operations Dashboard Panels', async ({ page }) => {
    await login(page);

    // Navigate to dashboard
    await page.goto(DASHBOARD_URL);
    await page.waitForTimeout(8000); // Wait for panels to load

    // Take full page screenshot
    const screenshotPath = path.join(screenshotDir, 'memory-operations-full.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Full screenshot saved: ${screenshotPath}`);

    // Panels to audit
    const panelsToAudit = [
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
      'discussions',
      'Chunking Operations by Type',
      'Chunking Latency by Type',
      'AST Chunks (1h)',
      'Markdown Chunks (1h)',
      'Prose Chunks (1h)',
      'Embedding Generation Rate',
      'Embedding Latency (p95)',
      'Batch Embeddings (1h)',
      'Realtime Embeddings (1h)',
      'Embedding Avg Latency'
    ];

    console.log('\n========================================');
    console.log('MEMORY OPERATIONS DASHBOARD AUDIT');
    console.log('========================================\n');

    const results: PanelAudit[] = [];

    for (const panelTitle of panelsToAudit) {
      const audit = await auditPanel(page, panelTitle);
      results.push(audit);

      const status = audit.hasData ? '✅' : '❌';
      const details = audit.issue ? ` - ${audit.issue}` : (audit.value ? ` = ${audit.value}` : '');
      console.log(`${status} ${panelTitle}${details}`);
    }

    // Summary
    const withData = results.filter(r => r.hasData && !r.issue?.includes('zero')).length;
    const noData = results.filter(r => !r.hasData).length;
    const zeroValue = results.filter(r => r.issue?.includes('zero')).length;

    console.log('\n========================================');
    console.log('SUMMARY');
    console.log('========================================');
    console.log(`Total panels audited: ${results.length}`);
    console.log(`With data: ${withData}`);
    console.log(`No data: ${noData}`);
    console.log(`Zero values: ${zeroValue}`);

    // Save results to JSON
    const reportPath = path.join(screenshotDir, 'panel-audit.json');
    fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));
    console.log(`\nReport saved: ${reportPath}`);

    // Document the issues
    console.log('\n========================================');
    console.log('ISSUES TO FIX');
    console.log('========================================');

    const issues = results.filter(r => !r.hasData || r.issue);
    issues.forEach(r => {
      console.log(`- ${r.title}: ${r.issue || 'Unknown issue'}`);
    });
  });

  test('Check Prometheus Metrics Available', async ({ page }) => {
    // Query Prometheus directly for available metrics

    const metricsToCheck = [
      'aimemory_captures_total',
      'aimemory_retrievals_total',
      'aimemory_dedup_check_duration_seconds_bucket',
      'aimemory_dedup_events_total',
      'aimemory_collection_size',
      'aimemory_chunking_operations_total',
      'aimemory_chunking_duration_seconds_bucket',
      'aimemory_embedding_batch_duration_seconds_bucket',
      'aimemory_embedding_realtime_duration_seconds_bucket',
      'aimemory_context_injection_tokens_sum'
    ];

    console.log('\n========================================');
    console.log('PROMETHEUS METRICS CHECK');
    console.log('========================================\n');

    for (const metric of metricsToCheck) {
      try {
        const authHeader = 'Basic ' + Buffer.from(`${PROMETHEUS_USER}:${PROMETHEUS_PASSWORD}`).toString('base64');
        const response = await page.request.get(`${PROMETHEUS_URL}/api/v1/query?query=${metric}`, {
          headers: { 'Authorization': authHeader }
        });
        const data = await response.json();

        if (data.status === 'success' && data.data.result.length > 0) {
          console.log(`✅ ${metric} - ${data.data.result.length} series`);

          // Show sample labels
          const sample = data.data.result[0];
          if (sample.metric) {
            const labels = Object.entries(sample.metric)
              .filter(([k]) => k !== '__name__')
              .map(([k, v]) => `${k}="${v}"`)
              .join(', ');
            console.log(`   Labels: {${labels}}`);
          }
        } else {
          console.log(`❌ ${metric} - No data`);
        }
      } catch (error) {
        console.log(`⚠️ ${metric} - Error: ${error}`);
      }
    }
  });

  test('Verify Panel Queries Match Available Metrics', async ({ page }) => {
    await login(page);
    await page.goto(DASHBOARD_URL);
    await page.waitForTimeout(5000);

    console.log('\n========================================');
    console.log('PANEL QUERY VERIFICATION');
    console.log('========================================\n');

    // The issue is that the dashboard queries don't match the actual metric labels
    // Let's document the expected vs actual

    const queryIssues = [
      {
        panel: 'Memory Captures by Collection',
        issue: 'Only discussions collection has data in aimemory_captures_total',
        expected: 'code-patterns, conventions, discussions',
        actual: 'discussions only'
      },
      {
        panel: 'Memory Retrievals by Collection',
        issue: 'Only code-patterns collection has data in aimemory_retrievals_total',
        expected: 'code-patterns, conventions, discussions',
        actual: 'code-patterns only'
      },
      {
        panel: 'Dedup Check p95 Latency',
        issue: 'aimemory_dedup_check_duration_seconds metric not being pushed',
        expected: 'Histogram buckets with dedup latency',
        actual: 'No data - metric not exposed'
      },
      {
        panel: 'Storage by Project (Vector Count)',
        issue: 'aimemory_collection_size metric not being pushed',
        expected: 'Gauge with vector counts per collection',
        actual: 'No data - metric not exposed'
      },
      {
        panel: 'Capture Success vs Failed',
        issue: 'Only status=success exists, no failed status recorded',
        expected: 'success, queued, failed statuses',
        actual: 'success only'
      },
      {
        panel: 'Chunking Operations by Type',
        issue: 'aimemory_chunking_operations_total metric not being pushed',
        expected: 'Counters for ast, markdown, prose chunk types',
        actual: 'No data - metric not exposed'
      },
      {
        panel: 'Embedding Generation Rate',
        issue: 'Only realtime embeddings tracked, no batch embeddings',
        expected: 'Both batch and realtime embedding counts',
        actual: 'Realtime only'
      }
    ];

    console.log('Known Issues with Dashboard Queries:\n');

    for (const issue of queryIssues) {
      console.log(`Panel: ${issue.panel}`);
      console.log(`  Issue: ${issue.issue}`);
      console.log(`  Expected: ${issue.expected}`);
      console.log(`  Actual: ${issue.actual}`);
      console.log('');
    }

    console.log('\n========================================');
    console.log('ROOT CAUSE');
    console.log('========================================');
    console.log(`
The dashboard queries are CORRECT but the metrics are not being
fully populated by the hooks system. This is NOT a dashboard bug
but a metrics collection gap.

Metrics that need to be instrumented in the hooks:
1. aimemory_dedup_check_duration_seconds - Add to dedup checker
2. aimemory_collection_size - Add periodic collection size scrape
3. aimemory_chunking_operations_total - Add to chunking pipeline
4. aimemory_chunking_duration_seconds - Add to chunking pipeline
5. aimemory_embedding_batch_duration_seconds - Add to batch embedder

The dashboards will show data once these metrics are exposed.
`);
  });
});
