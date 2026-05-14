# Live Functionality Testing

Consult this reference when a live functionality test is warranted — triggered when a new feature is complete, integration points are modified, configuration changes are made, or a bug fix was applied to user-facing behavior. Do not eager-load; load on demand only.

<when-to-recommend>
  <trigger>New feature implementation complete</trigger>
  <trigger>Integration points modified (APIs, hooks, services)</trigger>
  <trigger>Configuration changes made</trigger>
  <trigger>Bug fix applied to user-facing behavior</trigger>
</when-to-recommend>
<test-format>
  <section name="Test">[What to Test]</section>
  <section name="Prerequisites">[Service running, data seeded, etc.]</section>
  <section name="Steps">
    1. [Action] → **Expect**: [Observable result]
    2. [Next action] → **Expect**: [Observable result]
  </section>
  <section name="Success Criteria">
    - [ ] [What confirms it works]
    - [ ] [What confirms no regressions]
  </section>
  <section name="If It Fails">
    - [Likely cause 1]: [How to diagnose]
    - [Likely cause 2]: [How to diagnose]
  </section>
  <section name="Next">[What should happen after test passes]</section>
</test-format>
