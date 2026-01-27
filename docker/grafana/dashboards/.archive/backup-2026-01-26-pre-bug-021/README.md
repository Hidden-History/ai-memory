# Dashboard Backup: Pre-BUG-021 Implementation

**Date**: 2026-01-26
**Created by**: Amelia (Dev Agent)
**Reason**: Backup before BUG-021 complete dashboard redesign

## Backed Up Files

- `embedding-services.json` (14K)
- `memory-overview.json` (24K)
- `memory-performance.json` (15K)
- `system-health.json` (21K)

## Context

This backup was created before implementing BUG-021: Grafana Dashboard Complete Redesign.

**Changes planned:**
- Apply BP-041 (Grafana Dashboard Design Best Practices 2026)
- Template variables: `$project`, `$collection`, `$hook`, `$trigger`
- Fix histogram queries: `histogram_quantile(p, sum by (le) (...))`
- Apply BP-028: NO rate() on Pushgateway counters
- Apply BP-030: maxDataPoints 2000-5000 for sparse metrics
- Add panel descriptions to all panels
- Update for V2.0 memory system (11 hooks, 6 triggers, 3 collections, 15 memory types)

## Restore Instructions

If needed, restore from this backup:

```bash
cp docker/grafana/dashboards/.archive/backup-2026-01-26-pre-bug-021/*.json docker/grafana/dashboards/
docker compose -f docker/docker-compose.yml restart grafana
```

## Related

- BUG-021 specification: User message 2026-01-26
- BP-041: oversight/knowledge/best-practices/BP-041-grafana-dashboard-design-2026.md
- BP-041-TEMPLATES: oversight/knowledge/best-practices/BP-041-DASHBOARD-TEMPLATES.md
