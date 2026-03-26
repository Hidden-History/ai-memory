"""Version information for AI Memory Module.

Single source of truth for version number.
Follows PEP 440 and semantic versioning principles.
"""

__version__ = "2.2.6"
__version_info__ = tuple(int(part) for part in __version__.split("."))

# Version history:
# 2.2.6 - Multi-project installer fix: project-specific GitHub/Jira config (#85)
# 2.2.5 - Batch GitHub code blob sync, include/exclude overrides (#76/#77)
# 2.2.4 - Parzival V2.1 shim architecture, GitHub issue fixes (#73/#74/#75)
# 2.2.1 - Triple Fusion Hybrid Search (dense + sparse BM25 + ColBERT late interaction)
# 2.2.0 - Agent-activated injection architecture, Parzival V2 deployment
# 2.1.0 - Langfuse V3 SDK, agent identity, graceful shutdown
# 2.0.8 - Multi-project sync, credential hardening, Langfuse tracing
# 2.0.7 - Langfuse tracing (optional), stack.sh, 20 bug fixes
# 2.0.6 - Installation hardening, doc accuracy sprint
# 2.0.5 - CI hardening, Jira integration, security fixes
# 2.0.4 - Zero-truncation chunking, tech debt cleanup
# 2.0.3 - Bug fixes and stability improvements
# 1.0.0 - Initial release (Epic 7 complete)
