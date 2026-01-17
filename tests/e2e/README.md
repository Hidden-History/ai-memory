# Grafana Dashboard E2E Tests

Comprehensive Playwright tests for BMAD Memory Module Grafana dashboards.

## Prerequisites

1. **Grafana must be running** at http://localhost:23000
   ```bash
   docker compose -f docker/docker-compose.yml --profile monitoring up -d
   ```

2. **Install dependencies**
   ```bash
   npm install
   npx playwright install chromium
   ```

## Running Tests

### Run all tests (headless)
```bash
npm test
```

### Run tests with browser visible
```bash
npm run test:headed
```

### Open Playwright UI (interactive mode)
```bash
npm run test:ui
```

### Debug specific test
```bash
npm run test:debug -- --grep "should load BMAD Memory Overview"
```

### View test report
```bash
npm run test:report
```

## Test Coverage

### Authentication Tests
- ✅ Login to Grafana with admin credentials
- ✅ Handle password change skip dialog
- ✅ Verify successful authentication

### BMAD Memory Overview Dashboard
- ✅ Navigate to dashboard
- ✅ Verify 6 panels are visible:
  - Embedding Rate (last 1h)
  - Retrieval Rate (last 1h)
  - Collection Sizes
  - Total Memories Stored
  - Embedding/Retrieval Timeline
  - Operation Duration (Avg)
- ✅ Check data status for each panel
- ✅ Take full-page screenshot

### BMAD Memory Performance Dashboard
- ✅ Navigate to dashboard
- ✅ Verify 4 panels are visible:
  - Hook Duration (p50, p95, p99)
  - Embedding Duration Distribution
  - Retrieval Duration (p95)
  - Embedding Duration (p95)
- ✅ Verify "Success Rate by Component" is NOT present
- ✅ Check data status for each panel
- ✅ Take full-page screenshot

### Panel Configuration Tests
- ✅ Count panels on each dashboard
- ✅ Verify panel menus are accessible
- ✅ Document expected bmad_* metrics

### Comprehensive Report
- ✅ Generate JSON test report with all results
- ✅ Calculate success rate
- ✅ Provide detailed pass/fail status

## Test Output

### Screenshots
All screenshots are saved to `test-results/screenshots/`:
- `bmad-memory-overview.png` - Full-page screenshot of Overview dashboard
- `bmad-memory-performance.png` - Full-page screenshot of Performance dashboard

### Test Report
JSON report saved to `test-results/dashboard-test-report.json`:
```json
{
  "timestamp": "2026-01-15T...",
  "dashboards": {
    "overview": {
      "url": "http://localhost:23000/d/bmad-memory-overview/bmad-memory-overview",
      "panels": {
        "Embedding Rate (last 1h)": {
          "visible": true,
          "dataStatus": "no-data",
          "status": "PASS"
        },
        ...
      }
    },
    "performance": { ... }
  }
}
```

### HTML Report
Playwright generates an HTML report automatically:
```bash
npm run test:report
```

## Expected Test Results

### Panel Data Status
Each panel will show one of these statuses:
- **has-data** - Panel is displaying metrics
- **no-data** - Panel shows "No data" (expected for panels tracking operations that haven't occurred)
- **loading** - Panel is loading data
- **error** - Panel has an error

### Known Good States
- **Collection Sizes** panel should show data (142 total memories)
- **Total Memories Stored** may show "No data" if no storage operations occurred during test timeframe
- **Timeline** panels may show "No data" if no recent operations
- **Duration** panels may show "No data" if no operations occurred

## Troubleshooting

### Grafana not accessible
```bash
# Check if Grafana is running
docker compose -f docker/docker-compose.yml ps

# Check Grafana logs
docker compose -f docker/docker-compose.yml logs grafana

# Restart monitoring stack
docker compose -f docker/docker-compose.yml --profile monitoring restart
```

### Authentication fails
- Default credentials: `admin` / `admin`
- Test will automatically handle "skip password change" dialog
- Check Grafana logs for authentication errors

### Panels not loading
- Increase timeout in test (default: 15s)
- Check Prometheus is running and accessible at http://localhost:29090
- Verify metrics are being exported: http://localhost:28000/metrics

### Tests fail with "No data" on Collection Sizes
- This indicates a real issue - Collection Sizes should show data
- Check Prometheus query: `bmad_collection_size`
- Verify Prometheus is scraping monitoring API: http://localhost:28000/metrics

## CI/CD Integration

Tests can be run in CI with the following command:
```bash
CI=true npm test
```

This will:
- Enable retries (2 attempts per test)
- Generate HTML report
- Save screenshots/videos only on failure
- Exit with non-zero code on failure

## Development

### Adding New Tests
1. Create new test in `tests/e2e/`
2. Follow Page Object Model pattern
3. Use helper functions from `grafana-dashboards.spec.ts`
4. Add test tags for categorization

### Test Structure
```typescript
test.describe('Feature: [Feature Name]', () => {
  test.beforeEach(async ({ page }) => {
    // Setup
  });

  test('should [expected behavior]', async ({ page }) => {
    // Arrange
    // Act
    // Assert
  });
});
```

## References

- [Playwright Documentation](https://playwright.dev/)
- [Grafana Dashboard API](https://grafana.com/docs/grafana/latest/developers/http_api/dashboard/)
- [BMAD Memory Module Documentation](../../README.md)
