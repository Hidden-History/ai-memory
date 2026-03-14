---
name: "dev:pre-push"
description: >
  Pre-push validation and professional PR creation. Use when preparing to push code,
  creating pull requests, or running the full lint+test+security validation pipeline.
  Triggers on: "push", "pre-push", "validate before push", "create PR", "submit PR",
  "ready to push", "check before pushing". Runs ruff, black, isort, pytest, and
  security scans matching exact CI commands.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[--fix] [--pr] [--changed-only]"
---

# dev:pre-push — Pre-Push Validation and PR Creation

## Step 1: Git Hygiene Check

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Branch: $BRANCH"
git status --porcelain
git log main..HEAD --oneline
```

- If `$BRANCH` is `main` or `master`: STOP. Refuse to proceed — do not push directly to main.
- If `git status --porcelain` shows uncommitted changes: warn but continue.
- Record branch name and commit count for the summary.

## Step 2: Auto-Fix (if --fix)

If `$ARGUMENTS` contains `--fix`:

```bash
python3 -m black src/ tests/ scripts/
python3 -m isort --profile black src/ tests/ scripts/
python3 -m ruff check --fix src/ tests/ scripts/
```

Print results and proceed to Step 3.

If not `--fix`, proceed to Step 3 as check-only.

## Step 3: Lint Validation

Run the EXACT CI lint commands:

```bash
ruff check --output-format=github src/ tests/
black --check src/ tests/
isort --check-only --profile black src/ tests/
```

If ANY command fails:
- Show the specific errors.
- Suggest running `/dev:pre-push --fix` to auto-fix.
- STOP — do not proceed to Step 4.

## Step 4: Test Suite

Run the EXACT CI test command:

```bash
pytest tests/ -v --tb=short \
  --ignore=tests/e2e \
  --ignore=tests/integration \
  -m "not quarantine" \
  -p no:randomly \
  --cov=src/memory --cov-report=xml --cov-fail-under=70
```

If tests fail: show the failures and STOP.

## Step 5: Security Scan

Check changed files for hardcoded secrets:

```bash
git diff main..HEAD --name-only | while IFS= read -r f; do
  [ -f "$f" ] || continue
  grep -n 'api_key.*=.*["'"'"']sk-' "$f" 2>/dev/null && echo "WARN: possible secret in $f"
  grep -n 'api_key.*=.*["'"'"']key-' "$f" 2>/dev/null && echo "WARN: possible secret in $f"
  grep -n 'password.*=.*["'"'"'][^"'"'"']*["'"'"']' "$f" 2>/dev/null && echo "WARN: possible password in $f"
done
```

If any matches: warn (do not block — may be test fixtures).

## Step 6: Documentation Check

```bash
git diff main..HEAD --name-only | grep '^src/'
git diff main..HEAD --name-only | grep 'CHANGELOG.md'
```

- If `src/` files changed and `CHANGELOG.md` was NOT modified: warn.
- If `src/memory/__version__.py` exists: check that `README.md` version badge matches.
- Warn only — do not block.

## Step 7: Push Readiness Summary

Print a summary table:

```
## Pre-Push Validation Summary

| Check          | Status                        |
|----------------|-------------------------------|
| Git hygiene    | PASS/FAIL                     |
| Ruff lint      | PASS/FAIL                     |
| Black format   | PASS/FAIL                     |
| Isort imports  | PASS/FAIL                     |
| Unit tests     | PASS/FAIL (N passed, N failed)|
| Security scan  | PASS/WARN                     |
| Doc freshness  | PASS/WARN                     |

Branch: <branch-name> (N commits ahead of main)
Ready to push: YES/NO
```

If all checks pass and `$ARGUMENTS` does NOT contain `--pr`: print "All checks passed. Safe to push." and STOP.

## Step 8: PR Creation (if --pr)

Only execute if `$ARGUMENTS` contains `--pr`.

### 8.1 Push branch if not already pushed

```bash
git push -u origin HEAD
```

### 8.2 Analyze changes

```bash
git diff main...HEAD
git log main..HEAD --oneline
git diff main..HEAD --stat
```

### 8.3 Categorize commits

From `git log main..HEAD --oneline`, classify each commit as:
- **Added** — new features, new files
- **Changed** — modifications to existing functionality
- **Fixed** — bug fixes

### 8.4 Draft PR title

- Imperative mood, < 70 characters
- Derived from branch name and commit messages
- Conventional commit prefix if appropriate: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`

### 8.5 Create PR

```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
- [bullet points of changes]

## Changes
- N files changed, +X / -Y lines
- Added: [list]
- Changed: [list]
- Fixed: [list]

## Test plan
- [x] All unit tests pass locally (N passed)
- [x] Lint clean (ruff + black + isort)
- [x] Security scan clean
- [ ] CI green on this PR
- [ ] Live test from feature branch before merge
EOF
)"
```

**PR body constraints:**
- No "Co-Authored-By" lines
- No AI, agent, Claude, Parzival, BMAD, or tooling references
- No "Generated with" footers
- Professional, factual language only

### 8.6 Print PR URL

After `gh pr create` succeeds, print the PR URL.

---

## CI Parity

This skill runs the EXACT same commands as `.github/workflows/test.yml`.
If CI commands change, update this skill to match.

Commands sourced from:
- Lint: `test.yml` lines 39–46 (ruff, black, isort)
- Tests: `test.yml` lines 75–82 (pytest with ignore, marker, and coverage flags)
