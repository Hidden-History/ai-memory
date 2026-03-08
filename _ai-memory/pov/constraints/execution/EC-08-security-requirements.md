---
id: EC-08
name: Security Requirements Must Be Addressed for All Applicable Stories
severity: CRITICAL
phase: execution
---

# EC-08: Security Requirements Must Be Addressed for All Applicable Stories

## Constraint

Every story involving user input, authentication, data storage, or external calls must include security verification.

## Explanation

WHEN SECURITY VERIFICATION IS REQUIRED:
- Any story that accepts user input
- Any story that implements authentication or authorization
- Any story that stores or retrieves data
- Any story that makes external API calls
- Any story that handles file uploads or downloads
- Any story that exposes an API endpoint

SECURITY VERIFICATION CHECKLIST (for applicable stories):
- Input validation — all user input validated before use
- Output encoding — data encoded appropriately before output
- Authorization — correct permission checks in place
- Authentication — proper auth verification present
- Data protection — sensitive data handled per architecture security spec
- Injection protection — SQL, command, XSS vectors addressed
- Error handling — errors do not expose sensitive information
- Rate limiting — where specified in architecture

PARZIVAL ENFORCES:
- Security checklist is part of Phase 5 verification for applicable stories
- Any security gap is a legitimate issue (Category A2) — must fix
- Security issues are always CRITICAL priority
- Story is not complete with outstanding security issues

## Examples

**Permitted**:
- Running the security checklist for all applicable stories
- Treating any security gap as a CRITICAL legitimate issue

**Never permitted**:
- Skipping security verification for stories involving user input, auth, or data
- Treating security issues as non-critical
- Completing a story with outstanding security issues

## Enforcement

Parzival self-checks at every 10-message interval: "Have security requirements been addressed for applicable stories?"

## Violation Response

1. Run the security checklist for the applicable story
2. Any security gap is automatically CRITICAL priority
3. Add to review cycle fix list
4. Story is not complete until all security issues are resolved
