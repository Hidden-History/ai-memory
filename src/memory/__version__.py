"""Version information for AI Memory Module.

Single source of truth for version number.
Follows PEP 440 and semantic versioning principles.
"""

__version__ = "2.0.8"
__version_info__ = tuple(int(part) for part in __version__.split("."))

# Version history:
# 2.0.8 - Multi-project sync, credential hardening, Langfuse tracing
# 2.0.7 - Langfuse tracing (optional), stack.sh, 20 bug fixes
# 2.0.6 - Installation hardening, doc accuracy sprint
# 2.0.5 - CI hardening, Jira integration, security fixes
# 2.0.4 - Zero-truncation chunking, tech debt cleanup
# 2.0.3 - Bug fixes and stability improvements
# 1.0.0 - Initial release (Epic 7 complete)
