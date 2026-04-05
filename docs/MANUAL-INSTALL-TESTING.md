# Manual Installation Testing Checklist

These are manual tests that cannot be automated in pytest because they verify cross-platform installer behavior on Linux, macOS, and WSL2. They require a real shell environment, actual filesystem state, and platform-specific tooling that cannot be reliably reproduced in a unit or integration test harness.

This file was extracted from `tests/integration/test_hook_configuration.py::test_manual_testing_checklist` (deleted in Wave 3, TD-362, per BP-150 test-as-documentation decision tree option (a)).

---

## Platform Tests

- [ ] Test on Ubuntu 22.04/24.04
    - Run: `./install.sh`
    - Verify: `$HOME/.claude/settings.json` created
    - Check: All 3 hooks present with absolute paths

- [ ] Test on macOS (Intel)
    - Run: `./install.sh`
    - Verify: Hooks use `python3` (not `python`)

- [ ] Test on macOS (Apple Silicon)
    - Same as Intel test

- [ ] Test on WSL2
    - Run: `./install.sh` from WSL shell
    - Verify: Windows-side `.claude/settings.json` accessible

## Settings Preservation

- [ ] Test with existing settings.json
    - Create custom settings first
    - Run installer
    - Verify: Custom settings preserved, BMAD hooks added

- [ ] Test deduplication (run twice)
    - Run: `./install.sh`
    - Run: `./install.sh` again
    - Verify: No duplicate hooks in `settings.json`

- [ ] Test backup creation
    - Modify existing `settings.json`
    - Run installer
    - Verify: Backup created with timestamp

## Error Handling

- [ ] Test verification catches errors
    - Corrupt `settings.json` manually
    - Run installer
    - Verify: Install fails with clear error

- [ ] Test missing hook scripts
    - Delete one hook script
    - Run installer
    - Verify: Verification fails

---

*Origin: Extracted from `tests/integration/test_hook_configuration.py::test_manual_testing_checklist` per BP-150 test-as-documentation decision tree option (a). See TD-362. Story 7.2, AC 7.2.5.*
*Wave 3 origin commit: `0813a84` (r1 dev) / `4405545` (r2 fix for AST walk orelse scoping — Opus r1 review PLAN-023 P4b Wave 3).*
*BP-150: `oversight/knowledge/best-practices/BP-150-pytest-assert-true-replacement-importlib-prometheus-2026.md`*
