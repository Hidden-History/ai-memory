---
id: EC-10
name: Observability Requirements for New Code
severity: HIGH
phase: execution
---

# EC-10: Observability Requirements for New Code

## Constraint

Every new script, service, or feature MUST include observability from the start — structured logging, Prometheus metrics, and Grafana dashboard updates.

## Explanation

WHEN OBSERVABILITY IS REQUIRED:
- Any new hook script
- Any new API endpoint or service
- Any new background processor or worker
- Any new feature that introduces measurable operations

WHAT TO VERIFY — STRUCTURED LOGGING:
- Use `extra={}` dict pattern, not f-strings in log messages
- Include context fields: `session_id`, `memory_id`, `operation`, `duration_ms`
- Follow severity levels: DEBUG (traces), INFO (operations), WARNING (recoverable), ERROR (failures)

WHAT TO VERIFY — PROMETHEUS METRICS:
- Counter: Track operations (success/failure counts)
- Histogram: Track latencies (storage, search, embedding)
- Gauge: Track current state (queue size, connection status)
- Push via Pushgateway for short-lived scripts

WHAT TO VERIFY — GRAFANA DASHBOARD UPDATES:
- New metrics must be added to the relevant dashboard panel
- Dashboard location: `monitoring/grafana/dashboards/` (relative to project root)
- Include alerting thresholds where appropriate

IF MISSING:
- MUST instruct the implementing agent to add observability before story completion
- Observability items added via this enforcement are treated as part of the current story, not scope expansion

PARZIVAL ENFORCES:
- Observability checklist is included in agent instructions for every story involving new code
- Stories involving new scripts, services, or features are not complete without observability
- This complements EC-08 (security requirements) as a required inclusion for new implementations

OBSERVABILITY CHECKLIST (include in agent instructions for new code):
- [ ] Structured logging with `extra={}` pattern
- [ ] Context fields present: `session_id`, `memory_id`, `operation`, `duration_ms` (as applicable)
- [ ] Prometheus metrics defined (counter/histogram/gauge as appropriate)
- [ ] Pushgateway integration for short-lived scripts
- [ ] Dashboard panel or row added to `monitoring/grafana/dashboards/` (relative to project root)
- [ ] Alert threshold defined (if applicable)

## Examples

**Permitted**:
- New hook script → adds latency histogram + success/failure counters + dashboard panel
- New API endpoint → adds request latency + error rate + Grafana row
- Background processor → adds queue depth gauge + processing rate + alerting threshold

**Never permitted**:
- Implementing a new script without structured logging
- Adding a new metric without a corresponding Grafana panel
- Deferring observability to a follow-up story ("we'll add metrics later")

## Enforcement

Parzival self-checks at every 10-message interval: "EC-10: Does the current story involve new scripts, services, or features? If yes, have I included observability requirements in agent instructions?"

## Violation Response

1. Stop and assess: identify which observability areas are missing
2. Add the missing observability items to the agent's current instructions
3. Treat missing observability as a legitimate issue requiring resolution before story completion
4. Do not mark the story complete until all applicable checklist items are satisfied
