"""Minimal env loader for user-invoked CLI scripts outside the venv context.

Loads docker/.env then docker/.env.secrets (in precedence order matching
MemoryConfig.model_config tuple) into os.environ. Shell env wins over both
files. Missing files are silently skipped.

Precedence: shell env > docker/.env.secrets > docker/.env > Field defaults (BP-153 §3)

Usage:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _env_loader import load_install_env
    load_install_env()
    # module-level os.environ.get() calls follow
"""

import os
from pathlib import Path


def load_install_env() -> None:
    """Load split env files into os.environ before module-level os.environ.get() reads.

    Achieves precedence: shell env > docker/.env.secrets > docker/.env > defaults.
    Call once at the top of any script that reads os.environ directly and is
    invoked outside the install.sh subshell context (BUG-275 / BP-153 §3).
    """
    install_dir = Path(
        os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
    )
    docker_env = install_dir / "docker" / ".env"
    docker_secrets = install_dir / "docker" / ".env.secrets"

    # Iterate secrets first, then config — first-wins semantics achieve correct precedence:
    #   shell env already in os.environ → protected
    #   .env.secrets iterated first → non-empty keys land before .env keys
    #   .env iterated second → fills only keys not set by shell or secrets
    for env_path in [docker_secrets, docker_env]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if not val:
                    continue  # skip empty placeholders (mirrors env_ignore_empty=True)
                if key not in os.environ:
                    os.environ[key] = val
