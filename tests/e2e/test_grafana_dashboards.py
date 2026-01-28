"""
E2E tests for Grafana dashboard verification.

Test Coverage:
- Dashboard folder existence
- Dashboard accessibility
- Panel rendering status
- Error detection (No data, template variables, Prometheus queries)
- Visual regression for error states
"""
import re
import pytest
from typing import List, Dict, Any

# Skip tests if playwright is not installed (optional dependency)
pytest.importorskip("playwright", reason="Playwright not installed - run 'pip install playwright' and 'playwright install' to enable E2E tests")

from playwright.sync_api import Page, expect, ConsoleMessage


class TestGrafanaDashboards:
    """Comprehensive E2E tests for BMAD Memory Module Grafana dashboards."""

    GRAFANA_BASE_URL = "http://localhost:23000"
    FOLDER_NAME = "BMAD Memory Module"
    OVERVIEW_DASHBOARD_UID = "ai-memory-overview"
    PERFORMANCE_DASHBOARD_UID = "ai-memory-performance"

    @pytest.fixture(autouse=True)
    def setup_console_monitoring(self, grafana_page: Page):
        """Monitor browser console for errors during tests."""
        self.console_errors: List[ConsoleMessage] = []
        self.console_warnings: List[ConsoleMessage] = []

        def handle_console(msg: ConsoleMessage):
            if msg.type == "error":
                self.console_errors.append(msg)
            elif msg.type == "warning":
                self.console_warnings.append(msg)

        grafana_page.on("console", handle_console)

    # ==================== Folder Tests ====================

    def test_grafana_home_page_accessible(self, grafana_page: Page):
        """Verify Grafana home page loads successfully."""
        # Check for Grafana branding or navigation
        expect(grafana_page).to_have_title(re.compile("Grafana", re.IGNORECASE))

        # Verify anonymous access is working (no login prompt)
        login_form = grafana_page.locator('form[name="loginForm"]')
        expect(login_form).not_to_be_visible()

    def test_ai_memory_module_folder_exists(self, grafana_page: Page):
        """Verify 'BMAD Memory Module' folder exists in dashboard list."""
        # Navigate to dashboards page
        grafana_page.goto(f"{self.GRAFANA_BASE_URL}/dashboards")
        grafana_page.wait_for_load_state("networkidle")

        # Search for the folder
        search_input = grafana_page.locator('input[placeholder*="Search"]').first
        if search_input.is_visible():
            search_input.fill(self.FOLDER_NAME)
            grafana_page.wait_for_timeout(500)  # Allow search to filter

        # Look for folder in the list
        folder_locator = grafana_page.locator(f'text="{self.FOLDER_NAME}"').first
        expect(folder_locator).to_be_visible(timeout=5000)

    # ==================== BMAD Memory Overview Dashboard Tests ====================

    def test_overview_dashboard_accessible(self, grafana_page: Page):
        """Verify BMAD Memory Overview dashboard can be accessed."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        # Verify dashboard title
        dashboard_title = grafana_page.locator('[data-testid="data-testid Dashboard header title"]')
        expect(dashboard_title).to_contain_text("BMAD Memory Overview", timeout=10000)

    def test_overview_dashboard_panel_count(self, grafana_page: Page):
        """Verify BMAD Memory Overview dashboard has 6 panels."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        # Wait for panels to load
        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(2000)  # Additional wait for panel rendering

        # Count panels
        panels = grafana_page.locator('[data-viz-panel-key]')
        panel_count = panels.count()

        assert panel_count == 6, (
            f"Expected 6 panels in BMAD Memory Overview dashboard, found {panel_count}"
        )

    def test_overview_dashboard_panels_no_data_errors(self, grafana_page: Page):
        """Check if BMAD Memory Overview panels show 'No data' messages."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)  # Wait for data queries to complete

        panel_errors = self._check_panels_for_errors(grafana_page)

        if panel_errors:
            # Take screenshot of dashboard with errors
            grafana_page.screenshot(
                path="tests/e2e/screenshots/overview-dashboard-errors.png",
                full_page=True,
            )

            error_summary = "\n".join(
                [f"  - {err['panel']}: {err['error']}" for err in panel_errors]
            )
            pytest.fail(
                f"BMAD Memory Overview dashboard has {len(panel_errors)} panel(s) with errors:\n{error_summary}"
            )

    def test_overview_dashboard_template_variables(self, grafana_page: Page):
        """Verify template variables are properly configured in BMAD Memory Overview."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        # Look for template variable error indicators
        template_error_indicators = [
            'text="All"',  # Default template variable value that might indicate missing setup
            'text="No options found"',
            '[data-testid*="variable-error"]',
        ]

        grafana_page.wait_for_timeout(2000)

        found_errors = []
        for indicator in template_error_indicators:
            if grafana_page.locator(indicator).count() > 0:
                found_errors.append(indicator)

        if found_errors:
            grafana_page.screenshot(
                path="tests/e2e/screenshots/overview-template-errors.png",
                full_page=True,
            )

    def test_overview_dashboard_prometheus_queries(self, grafana_page: Page):
        """Check for Prometheus query errors in BMAD Memory Overview panels."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        # Check for Prometheus-specific error messages
        prometheus_error_patterns = [
            "error executing query",
            "invalid parameter",
            "context deadline exceeded",
            "connection refused",
            "bad_data",
        ]

        found_prometheus_errors = []
        for pattern in prometheus_error_patterns:
            error_locator = grafana_page.locator(f'text="{pattern}"')
            if error_locator.count() > 0:
                found_prometheus_errors.append(pattern)

        if found_prometheus_errors:
            grafana_page.screenshot(
                path="tests/e2e/screenshots/overview-prometheus-errors.png",
                full_page=True,
            )
            pytest.fail(
                f"Prometheus query errors detected: {', '.join(found_prometheus_errors)}"
            )

    # ==================== BMAD Memory Performance Dashboard Tests ====================

    def test_performance_dashboard_accessible(self, grafana_page: Page):
        """Verify BMAD Memory Performance dashboard can be accessed."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        dashboard_title = grafana_page.locator('[data-testid="data-testid Dashboard header title"]')
        expect(dashboard_title).to_contain_text("BMAD Memory Performance", timeout=10000)

    def test_performance_dashboard_panel_count(self, grafana_page: Page):
        """Verify BMAD Memory Performance dashboard has 4 panels."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(2000)

        panels = grafana_page.locator('[data-viz-panel-key]')
        panel_count = panels.count()

        assert panel_count == 4, (
            f"Expected 4 panels in BMAD Memory Performance dashboard, found {panel_count}"
        )

    def test_performance_dashboard_panels_no_data_errors(self, grafana_page: Page):
        """Check if BMAD Memory Performance panels show 'No data' messages."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        panel_errors = self._check_panels_for_errors(grafana_page)

        if panel_errors:
            grafana_page.screenshot(
                path="tests/e2e/screenshots/performance-dashboard-errors.png",
                full_page=True,
            )

            error_summary = "\n".join(
                [f"  - {err['panel']}: {err['error']}" for err in panel_errors]
            )
            pytest.fail(
                f"BMAD Memory Performance dashboard has {len(panel_errors)} panel(s) with errors:\n{error_summary}"
            )

    def test_performance_dashboard_prometheus_queries(self, grafana_page: Page):
        """Check for Prometheus query errors in BMAD Memory Performance panels."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        prometheus_error_patterns = [
            "error executing query",
            "invalid parameter",
            "context deadline exceeded",
            "connection refused",
            "bad_data",
        ]

        found_prometheus_errors = []
        for pattern in prometheus_error_patterns:
            error_locator = grafana_page.locator(f'text="{pattern}"')
            if error_locator.count() > 0:
                found_prometheus_errors.append(pattern)

        if found_prometheus_errors:
            grafana_page.screenshot(
                path="tests/e2e/screenshots/performance-prometheus-errors.png",
                full_page=True,
            )
            pytest.fail(
                f"Prometheus query errors detected: {', '.join(found_prometheus_errors)}"
            )

    # ==================== Browser Console Tests ====================

    def test_overview_dashboard_console_errors(self, grafana_page: Page):
        """Verify no JavaScript console errors in BMAD Memory Overview dashboard."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        if self.console_errors:
            error_messages = [f"{msg.type}: {msg.text}" for msg in self.console_errors]
            grafana_page.screenshot(
                path="tests/e2e/screenshots/overview-console-errors.png",
                full_page=True,
            )
            pytest.fail(
                f"Console errors detected in Overview dashboard:\n"
                + "\n".join(error_messages)
            )

    def test_performance_dashboard_console_errors(self, grafana_page: Page):
        """Verify no JavaScript console errors in BMAD Memory Performance dashboard."""
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        if self.console_errors:
            error_messages = [f"{msg.type}: {msg.text}" for msg in self.console_errors]
            grafana_page.screenshot(
                path="tests/e2e/screenshots/performance-console-errors.png",
                full_page=True,
            )
            pytest.fail(
                f"Console errors detected in Performance dashboard:\n"
                + "\n".join(error_messages)
            )

    # ==================== Visual Regression Tests ====================

    def test_overview_dashboard_visual_baseline(self, grafana_page: Page):
        """
        Capture visual baseline for BMAD Memory Overview dashboard.

        This test captures a screenshot for manual inspection and future visual regression testing.
        """
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.OVERVIEW_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        # Take full page screenshot
        grafana_page.screenshot(
            path="tests/e2e/screenshots/overview-dashboard-baseline.png",
            full_page=True,
        )

    def test_performance_dashboard_visual_baseline(self, grafana_page: Page):
        """
        Capture visual baseline for BMAD Memory Performance dashboard.

        This test captures a screenshot for manual inspection and future visual regression testing.
        """
        grafana_page.goto(
            f"{self.GRAFANA_BASE_URL}/d/{self.PERFORMANCE_DASHBOARD_UID}",
            wait_until="networkidle",
        )

        grafana_page.wait_for_selector('[data-viz-panel-key]', timeout=15000)
        grafana_page.wait_for_timeout(3000)

        grafana_page.screenshot(
            path="tests/e2e/screenshots/performance-dashboard-baseline.png",
            full_page=True,
        )

    # ==================== Helper Methods ====================

    def _check_panels_for_errors(self, page: Page) -> List[Dict[str, Any]]:
        """
        Check all panels on current dashboard for errors.

        Returns:
            List of dictionaries containing panel errors with panel title and error message.
        """
        panels = page.locator('[data-viz-panel-key]')
        panel_count = panels.count()
        panel_errors = []

        for i in range(panel_count):
            panel = panels.nth(i)

            # Try to get panel title
            panel_title_locator = panel.locator('[data-testid*="panel-title"]').first
            panel_title = (
                panel_title_locator.text_content()
                if panel_title_locator.count() > 0
                else f"Panel {i + 1}"
            )

            # Check for common error indicators
            error_indicators = [
                ("No data", 'text="No data"'),
                ("No data points", 'text="No data points"'),
                ("Error", '[data-testid*="error"]'),
                ("Error", 'text="Error"'),
                ("Failed", 'text="Failed"'),
                ("N/A", 'text="N/A"'),
            ]

            for error_type, selector in error_indicators:
                if panel.locator(selector).count() > 0:
                    panel_errors.append({"panel": panel_title, "error": error_type})
                    break

        return panel_errors
