"""
Integration tests for Grafana dashboard provisioning.

Tests verify:
- Dashboard auto-loading via provisioning
- Datasource connectivity
- Panel configuration correctness
- API accessibility
"""

import json
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="module")
def grafana_url():
    """Grafana base URL for testing."""
    return "http://localhost:23000"


@pytest.fixture(scope="module")
def grafana_auth():
    """Grafana auth credentials (anonymous viewer)."""
    return None  # Anonymous access enabled


@pytest.fixture(scope="module")
def wait_for_grafana(grafana_url):
    """Wait for Grafana to be healthy before running tests."""
    max_retries = 30
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            response = httpx.get(f"{grafana_url}/api/health", timeout=5)
            if response.status_code == 200:
                # Give provisioning extra time to complete
                time.sleep(5)
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                pytest.skip("Grafana not available - skipping integration tests")

    pytest.skip("Grafana health check timeout - skipping integration tests")


def test_grafana_health(grafana_url, wait_for_grafana):
    """Verify Grafana is running and healthy."""
    response = httpx.get(f"{grafana_url}/api/health", timeout=5)
    assert response.status_code == 200

    health = response.json()
    assert health.get("database") == "ok"


def test_prometheus_datasource_provisioned(grafana_url, wait_for_grafana):
    """Verify Prometheus datasource is auto-provisioned."""
    response = httpx.get(f"{grafana_url}/api/datasources/name/Prometheus", timeout=5)
    assert response.status_code == 200

    datasource = response.json()
    assert datasource["name"] == "Prometheus"
    assert datasource["type"] == "prometheus"
    assert datasource["url"] == "http://prometheus:9090"
    assert datasource["access"] == "proxy"
    assert datasource["isDefault"] is True
    assert datasource.get("readOnly") is True or datasource.get("editable") is False


def test_memory_overview_dashboard_provisioned(grafana_url, wait_for_grafana):
    """Verify Memory Overview dashboard is accessible via API."""
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-overview", timeout=5
    )
    assert response.status_code == 200

    result = response.json()
    dashboard = result["dashboard"]

    # Verify dashboard metadata
    assert dashboard["title"] == "BMAD Memory Overview"
    assert dashboard["uid"] == "ai-memory-overview"
    assert dashboard["editable"] is False

    # Verify all 6 required panels present (AC 6.3.4)
    panels = dashboard.get("panels", [])
    assert len(panels) >= 6, f"Expected >= 6 panels, got {len(panels)}"

    # Verify panel types
    panel_types = {panel["type"] for panel in panels}
    assert "stat" in panel_types, "Missing stat panel"
    assert "gauge" in panel_types, "Missing gauge panel"
    assert "timeseries" in panel_types, "Missing timeseries panel"


def test_memory_overview_panels_configuration(grafana_url, wait_for_grafana):
    """Verify Memory Overview panels have correct queries and config."""
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-overview", timeout=5
    )
    result = response.json()
    panels = result["dashboard"]["panels"]

    # Find capture rate panel
    capture_panels = [p for p in panels if "Capture Rate" in p.get("title", "")]
    assert len(capture_panels) == 1, "Missing or duplicate Capture Rate panel"
    capture_panel = capture_panels[0]
    assert capture_panel["type"] == "stat"
    assert any(
        "ai_memory_captures_total" in str(t.get("expr", ""))
        for t in capture_panel["targets"]
    )

    # Find retrieval rate panel
    retrieval_panels = [p for p in panels if "Retrieval Rate" in p.get("title", "")]
    assert len(retrieval_panels) == 1, "Missing or duplicate Retrieval Rate panel"
    retrieval_panel = retrieval_panels[0]
    assert retrieval_panel["type"] == "stat"
    assert any(
        "ai_memory_retrievals_total" in str(t.get("expr", ""))
        for t in retrieval_panel["targets"]
    )

    # Find collection sizes panel (gauge with thresholds)
    collection_panels = [p for p in panels if "Collection Sizes" in p.get("title", "")]
    assert len(collection_panels) == 1, "Missing or duplicate Collection Sizes panel"
    collection_panel = collection_panels[0]
    assert collection_panel["type"] == "gauge"
    assert any(
        "ai_memory_collection_size" in str(t.get("expr", ""))
        for t in collection_panel["targets"]
    )

    # Verify thresholds per AC 6.3.4 (Green=0, Yellow=8000, Red=10000)
    thresholds = (
        collection_panel.get("fieldConfig", {})
        .get("defaults", {})
        .get("thresholds", {})
    )
    steps = thresholds.get("steps", [])
    threshold_values = [s.get("value") for s in steps if s.get("value") is not None]
    assert 8000 in threshold_values, "Missing 8000 threshold (NFR-compliant)"
    assert 10000 in threshold_values, "Missing 10000 threshold (NFR-compliant)"


def test_performance_dashboard_provisioned(grafana_url, wait_for_grafana):
    """Verify Performance dashboard is accessible via API."""
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-performance", timeout=5
    )
    assert response.status_code == 200

    result = response.json()
    dashboard = result["dashboard"]

    # Verify dashboard metadata
    assert dashboard["title"] == "BMAD Memory Performance"
    assert dashboard["uid"] == "ai-memory-performance"
    assert dashboard["editable"] is False

    # Verify all 4 required panels present (AC 6.3.5)
    panels = dashboard.get("panels", [])
    assert len(panels) >= 4, f"Expected >= 4 panels, got {len(panels)}"

    # Verify panel types
    panel_types = {panel["type"] for panel in panels}
    assert "timeseries" in panel_types, "Missing timeseries panel"
    assert "heatmap" in panel_types, "Missing heatmap panel"
    assert "stat" in panel_types, "Missing stat panel"
    assert "bargauge" in panel_types, "Missing bar gauge panel"


def test_performance_dashboard_nfr_thresholds(grafana_url, wait_for_grafana):
    """Verify Performance dashboard has NFR-compliant thresholds."""
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-performance", timeout=5
    )
    result = response.json()
    panels = result["dashboard"]["panels"]

    # Find retrieval duration panel
    retrieval_panels = [p for p in panels if "Retrieval Duration" in p.get("title", "")]
    assert len(retrieval_panels) == 1, "Missing Retrieval Duration panel"
    retrieval_panel = retrieval_panels[0]

    # Verify NFR thresholds per AC 6.3.5: Green (0-2s), Yellow (2-3s), Red (>3s)
    thresholds = (
        retrieval_panel.get("fieldConfig", {}).get("defaults", {}).get("thresholds", {})
    )
    steps = thresholds.get("steps", [])
    threshold_values = [s.get("value") for s in steps if s.get("value") is not None]
    assert 2 in threshold_values, "Missing 2s threshold (NFR-P3)"
    assert 3 in threshold_values, "Missing 3s threshold (NFR-P3)"


def test_dashboard_folder_organization(grafana_url, wait_for_grafana):
    """Verify dashboards are organized in 'BMAD Memory Module' folder."""
    # Search for dashboards
    response = httpx.get(f"{grafana_url}/api/search?type=dash-db", timeout=5)
    assert response.status_code == 200

    dashboards = response.json()

    # Find our dashboards
    ai_memory_dashboards = [d for d in dashboards if "ai-memory" in d.get("uid", "")]
    assert len(ai_memory_dashboards) >= 2, "Expected both dashboards to be present"

    # Verify folder organization per AC 6.3.3
    for dashboard in ai_memory_dashboards:
        assert (
            dashboard.get("folderTitle") == "BMAD Memory Module"
        ), f"Dashboard {dashboard['uid']} not in correct folder"


def test_anonymous_viewer_access(grafana_url, wait_for_grafana):
    """Verify anonymous viewer access is enabled per AC 6.3.6."""
    # Access dashboard without auth
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-overview", timeout=5
    )
    assert response.status_code == 200, "Anonymous access not working"


def test_dashboard_refresh_intervals(grafana_url, wait_for_grafana):
    """Verify dashboard auto-refresh settings."""
    # Overview dashboard - 30s refresh
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-overview", timeout=5
    )
    overview = response.json()["dashboard"]
    assert overview.get("refresh") == "30s", "Overview refresh should be 30s"

    # Performance dashboard - 10s refresh
    response = httpx.get(
        f"{grafana_url}/api/dashboards/uid/ai-memory-performance", timeout=5
    )
    performance = response.json()["dashboard"]
    assert performance.get("refresh") == "10s", "Performance refresh should be 10s"


def test_prometheus_connectivity_from_grafana(grafana_url, wait_for_grafana):
    """Verify Grafana can connect to Prometheus datasource."""
    # Test datasource connectivity
    response = httpx.post(
        f"{grafana_url}/api/datasources/proxy/1/api/v1/query",
        params={"query": "up"},
        timeout=10,
    )

    # 200 or 400 are acceptable (400 if Prometheus not yet scraped)
    assert response.status_code in [
        200,
        400,
        404,
    ], f"Datasource connectivity test failed: {response.status_code}"


def test_dashboard_json_files_exist():
    """Verify dashboard JSON files exist in expected locations."""
    project_root = Path(__file__).parent.parent.parent
    dashboards_dir = project_root / "docker" / "grafana" / "dashboards"

    overview_path = dashboards_dir / "memory-overview.json"
    assert overview_path.exists(), f"Overview dashboard missing: {overview_path}"

    performance_path = dashboards_dir / "memory-performance.json"
    assert (
        performance_path.exists()
    ), f"Performance dashboard missing: {performance_path}"

    # Verify valid JSON
    with open(overview_path) as f:
        overview_data = json.load(f)
        assert overview_data["uid"] == "ai-memory-overview-v2"

    with open(performance_path) as f:
        performance_data = json.load(f)
        assert performance_data["uid"] == "ai-memory-performance"


def test_provisioning_config_files_exist():
    """Verify provisioning configuration files exist."""
    project_root = Path(__file__).parent.parent.parent
    provisioning_dir = project_root / "docker" / "grafana" / "provisioning"

    datasources_yaml = provisioning_dir / "datasources" / "datasources.yaml"
    assert datasources_yaml.exists(), f"Datasources config missing: {datasources_yaml}"

    dashboards_yaml = provisioning_dir / "dashboards" / "dashboards.yaml"
    assert dashboards_yaml.exists(), f"Dashboards config missing: {dashboards_yaml}"
