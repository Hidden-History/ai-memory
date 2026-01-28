# Security Policy

## Supported Versions

We actively support the following versions of AI Memory Module with security updates:

| Version | Supported          | End of Support |
| ------- | ------------------ | -------------- |
| 1.x.x   | :white_check_mark: | TBD            |
| < 1.0   | :x:                | 2026-01-14     |

**Note:** We recommend always using the latest stable release for the best security posture.

---

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in AI Memory Module, please help us address it responsibly.

### ⚠️ DO NOT create a public GitHub issue for security vulnerabilities

### How to Report

**Email:** security@wbsolutions.ca

**Subject Line:** `[SECURITY] AI Memory Module - [Brief Description]`

**Include in your report:**

1. **Description of the vulnerability**
   - What is the issue?
   - What impact does it have?

2. **Steps to reproduce**
   - Detailed instructions to reproduce the vulnerability
   - Include sample code, payloads, or configuration if applicable

3. **Affected versions**
   - Which versions are affected?
   - Have you tested multiple versions?

4. **Suggested fix (optional)**
   - If you have a proposed solution, we'd love to hear it

5. **Your contact information**
   - How can we reach you for clarification?

### What to Expect

1. **Acknowledgment:** We'll acknowledge receipt within **48 hours**

2. **Initial assessment:** We'll provide an initial assessment within **5 business days**, including:
   - Severity classification (Critical, High, Medium, Low)
   - Estimated timeline for fix
   - Whether we need more information

3. **Resolution:**
   - **Critical vulnerabilities:** Patch within 7 days
   - **High severity:** Patch within 14 days
   - **Medium/Low severity:** Patch in next minor release

4. **Credit:** We'll credit you in the security advisory (unless you prefer to remain anonymous)

### Coordinated Disclosure

We believe in coordinated disclosure:

- We'll work with you to understand the issue
- We'll develop and test a fix
- We'll prepare a security advisory
- We'll release the fix and advisory simultaneously
- **We ask that you do not publicly disclose the vulnerability until we've released a fix**

Typical timeline: **90 days** from initial report to public disclosure

---

## Security Best Practices

When deploying AI Memory Module, follow these security best practices:

### 1. Network Security

- **Isolate Docker network:** Use a dedicated Docker network for AI Memory services
  ```bash
  docker network create ai-memory-net
  ```

- **Firewall rules:** Restrict access to service ports (26350, 28080, 28501)
  ```bash
  # Only allow localhost access
  sudo ufw deny 26350
  sudo ufw deny 28080
  sudo ufw deny 28501
  ```

- **Use SSH tunneling** for remote access instead of exposing ports:
  ```bash
  ssh -L 28501:localhost:28501 user@remote-server
  ```

### 2. Access Control

- **Qdrant API keys:** Enable authentication for Qdrant (production deployments)
  ```yaml
  # docker/.env
  QDRANT_API_KEY=your-secure-key-here
  ```

- **Read-only dashboards:** Configure Grafana in viewer mode for non-admins

- **File permissions:** Ensure hook scripts have appropriate permissions
  ```bash
  chmod 750 .claude/hooks/scripts/*.py
  ```

### 3. Data Security

- **Encrypt sensitive memories:** Consider encrypting memories containing credentials before storage

- **Regular backups:** Back up Qdrant data directory regularly
  ```bash
  docker run --rm -v qdrant_storage:/data -v $(pwd)/backup:/backup \
    alpine tar czf /backup/qdrant-backup-$(date +%Y%m%d).tar.gz /data
  ```

- **Sanitize inputs:** Review memories before they're stored to avoid leaking secrets

### 4. Docker Security

- **Use official images:** Only use official Qdrant and Python base images

- **Keep images updated:** Regularly update base images
  ```bash
  docker compose pull
  docker compose up -d
  ```

- **Scan for vulnerabilities:**
  ```bash
  docker scan qdrant/qdrant:latest
  ```

- **Run as non-root:** Docker containers run as non-root users (already configured)

### 5. Dependency Security

- **Monitor dependencies:** Use Dependabot (enabled by default on GitHub)

- **Audit Python packages:**
  ```bash
  pip install pip-audit
  pip-audit -r requirements-dev.txt
  ```

- **Pin versions:** Use exact versions in requirements files (already done)

### 6. Secrets Management

**Never commit:**
- `.env` files
- API keys
- Credentials
- Personal access tokens

**Use environment variables:**
```bash
export QDRANT_API_KEY="$(openssl rand -hex 32)"
```

**Rotate secrets regularly:** Change API keys every 90 days (production)

---

## Security Features

AI Memory Module includes these security features:

### Built-in Protections

1. **Input validation:** All user inputs are validated before processing
2. **Content sanitization:** Code is sanitized before storage to prevent injection
3. **Graceful degradation:** Security failures don't expose sensitive data
4. **Minimal attack surface:** Hook scripts run with minimal permissions
5. **Isolated execution:** Docker containers are isolated from host system

### Monitoring

Security-relevant metrics are tracked:

- Failed connection attempts to Qdrant
- Abnormal query patterns
- Memory storage anomalies
- Service health status

Access these via Grafana: `http://localhost:23000`

---

## Known Security Considerations

### Current Limitations

1. **No built-in authentication:** Qdrant runs without auth by default (localhost only)
   - **Mitigation:** Enable Qdrant API keys for production deployments

2. **Plaintext storage:** Memories are stored unencrypted in Qdrant
   - **Mitigation:** Use encrypted filesystems or Qdrant's upcoming encryption features

3. **Local-only design:** Designed for single-user, local development
   - **Mitigation:** Don't expose services to untrusted networks

### Future Enhancements

Planned security improvements (see ROADMAP.md):

- [ ] End-to-end encryption for sensitive memories (v1.2.0)
- [ ] Built-in API key management (v1.2.0)
- [ ] Role-based access control (v2.0.0)
- [ ] SSO integration (v2.0.0)
- [ ] Audit logging (v2.0.0)

---

## Security Audit History

| Date       | Auditor          | Scope          | Findings | Status   |
|------------|------------------|----------------|----------|----------|
| 2026-01-14 | Internal Review  | Initial Release| 0 Critical| Resolved |

---

## Contact

**Security Team:** security@wbsolutions.ca
**General Contact:** info@wbsolutions.ca
**Website:** https://wbsolutions.ca

---

## Acknowledgments

We thank the following security researchers for responsibly disclosing vulnerabilities:

_No reported vulnerabilities yet - you could be the first to help secure AI Memory Module!_

---

**Last Updated:** 2026-01-14
**Policy Version:** 1.0
