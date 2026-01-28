# Docker Security Templates

**Purpose**: Reusable security hardening patterns for Docker services in AI Memory Module.

---

## Overview

This directory contains security templates for Docker Compose services. All templates follow 2026 best practices established in Epic 6 Story 6.3 and documented in DEC-012.

---

## Files

| File | Purpose |
|------|---------|
| `secure-service.yml` | Security hardening template for all new Docker services |

---

## Usage

### For New Services

When creating a new Docker service in `docker/docker-compose.yml`:

1. **Copy the required security settings** from `secure-service.yml`
2. **Apply ALL required settings** (security_opt, cap_drop)
3. **Apply recommended settings** where applicable (read_only, user, tmpfs)
4. **Add CSRF protection** for web UI services

### Example: Adding a New Service

```yaml
my-new-service:
  image: myservice:latest
  container_name: memory-my-service

  # Required security hardening (from template)
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL

  # Recommended (where applicable)
  read_only: true
  tmpfs:
    - /tmp:rw,noexec,nosuid
  user: "1000:1000"

  # Service-specific configuration
  ports:
    - "127.0.0.1:28XXX:8000"
  environment:
    - MY_CONFIG=value
  restart: unless-stopped
```

---

## Security Settings Explained

### Required for ALL Services

#### `security_opt: no-new-privileges:true`

Prevents privilege escalation attacks. The container cannot gain additional privileges beyond what it starts with.

**Why**: Blocks privilege escalation exploits like setuid binaries.

#### `cap_drop: ALL`

Drops all Linux capabilities. Services run with minimal kernel privileges.

**Why**: Reduces attack surface by removing unnecessary kernel-level permissions.

---

### Recommended Settings

#### `read_only: true`

Makes the container's root filesystem read-only.

**When to use**: Services that don't write to root filesystem (most services).
**Exception**: Services needing writable root (use tmpfs for /tmp instead).

**Why**: Prevents attackers from modifying binaries or installing malware.

#### `tmpfs: /tmp:rw,noexec,nosuid`

Provides writable temporary storage with security restrictions.

**When to use**: With `read_only: true` for services needing /tmp writes.
**Flags**:
- `rw`: Read-write access
- `noexec`: Prevents executing binaries from /tmp
- `nosuid`: Ignores setuid/setgid bits

**Why**: Allows temporary files while blocking common attack vectors.

#### `user: "1000:1000"`

Runs container as non-root user.

**When to use**: Always, unless service explicitly requires root.
**Adjust**: Use appropriate UID:GID for service requirements.

**Why**: Limits damage if container is compromised.

---

### Web UI Specific

#### CSRF Protection

For services with web UIs (Grafana, Streamlit, custom dashboards):

**Grafana**:
```yaml
environment:
  - GF_SECURITY_CSRF_ALWAYS_CHECK=true
  - GF_SNAPSHOTS_EXTERNAL_ENABLED=false
```

**Generic web services**:
```yaml
environment:
  - CSRF_PROTECTION=true
```

**Why**: Prevents cross-site request forgery attacks.

---

## Existing Service Examples

Reference these services in `docker/docker-compose.yml` for complete examples:

- **monitoring-api**: Full security hardening with read_only and tmpfs
- **grafana**: Web UI with CSRF protection
- **prometheus**: Standard hardening without read_only (needs config writes)
- **streamlit**: Web UI with security hardening

---

## Verification Checklist

When adding or reviewing Docker services, verify:

- [ ] `security_opt: no-new-privileges:true` present
- [ ] `cap_drop: ALL` present
- [ ] `read_only: true` used if service doesn't write to root
- [ ] `tmpfs` configured if using `read_only: true`
- [ ] `user` specified (non-root)
- [ ] CSRF protection enabled for web UIs

This checklist is also included in `oversight/verification/checklists/code-review.md` under "Docker Security Hardening".

---

## References

- **DEC-012**: Security hardening architecture decision
- **Epic 6 Story 6.3**: Initial security hardening implementation
- **Epic 6 Retrospective**: ACT-005 action item
- **Project Standards**: `_bmad-output/project-context.md` (Docker security rules)

---

**Last Updated**: 2026-01-13
**Version**: 1.0.0
