"""Pytest configuration for E2E tests."""

import os
from collections.abc import Generator

import pytest

# Optional playwright imports for Grafana E2E tests
try:
    from playwright.sync_api import Browser, BrowserContext, Page

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None  # type: ignore
    BrowserContext = None  # type: ignore
    Browser = None  # type: ignore


@pytest.fixture(scope="session", autouse=True)
def _ensure_screenshot_dirs():
    """Create output directories required by E2E tests (TD-219)."""
    os.makedirs("tests/e2e/screenshots", exist_ok=True)


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context for all E2E tests."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    return {
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
        "record_video_dir": "tests/e2e/videos",
        "record_video_size": {"width": 1920, "height": 1080},
    }


@pytest.fixture(scope="function")
def grafana_page(page: Page) -> Generator[Page, None, None]:
    """
    Provide a page navigated to Grafana home.

    Grafana should be accessible at http://localhost:23000 with anonymous access enabled.
    """
    page.goto("http://localhost:23000", wait_until="networkidle", timeout=30000)

    # Wait for Grafana to be fully loaded - look for common Grafana UI elements
    # Try multiple selectors as Grafana UI can vary by version
    try:
        page.wait_for_selector('nav, [role="navigation"], .sidemenu', timeout=10000)
    except Exception:
        # If navigation isn't found, just wait for page load
        page.wait_for_load_state("domcontentloaded")

    yield page
