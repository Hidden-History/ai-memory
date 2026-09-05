"""The v2.0.5->v2.0.6 migration must seed NO cause and NO condition.

Story 1.1 / AD-32 / NORMATIVE rule 4. The migration finds an existing
``PARZIVAL_ENABLED`` and no record of why it holds that value. Every option that
writes something is wrong, and the two wrong options fail differently:

* Seeding ``opt-out`` is what rule 4 forbids **by name** -- it tells every operator
  whose install *failed* that they chose it, which is precisely the conflation this
  record exists to remove.
* Seeding the **empty string** looks safe and is not, because ``update_env_file``
  appends **per key**. On an install already carrying ``PARZIVAL_ENABLED=true`` the
  value key is skipped as already-present while the cause key is appended --
  producing the ``(enabled x non-empty cause)`` cell directly on the first, and
  producing a partial record this story explicitly defers to Story 1.2 on the rest.

So the migration seeds only the value. Absent cause resolves to ``unknown`` through
every reader, which is the honest answer: this install did not record why.

This module is also the one the enablement-record module's docstring points at. An
earlier revision claimed write-site 6 "is exercised in its own test module" when no
such module existed -- a false statement standing guard over an untested site.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_MIGRATION = _REPO / "scripts" / "migrate_v205_to_v206.py"

sys.path.insert(0, str(_REPO / "src"))

from memory.parzival_state import normalize_cause  # noqa: E402


@pytest.fixture
def migration(monkeypatch, tmp_path):
    """Load the migration script with INSTALL_DIR pointed at a temp dir."""
    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    for key in [k for k in sys.modules if "migrate_v205_to_v206" in k]:
        monkeypatch.delitem(sys.modules, key, raising=False)
    spec = importlib.util.spec_from_file_location("migrate_v205_to_v206", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "INSTALL_DIR", tmp_path)
    return module


class TestParzivalVarsCarriesNoCause:
    def test_cause_and_condition_are_absent_from_parzival_vars(self, migration):
        keys = [key for key, _ in migration.PARZIVAL_VARS]
        assert "PARZIVAL_ENABLED" in keys, keys
        assert "PARZIVAL_ENABLED_CAUSE" not in keys, (
            "The migration cannot know the cause. Seeding one either manufactures "
            "`opt-out` for a failed install (NORMATIVE rule 4) or writes the "
            "forbidden cell directly, since update_env_file appends per key."
        )
        assert "PARZIVAL_ENABLED_CONDITION" not in keys, (
            "`partial` is produced by Story 1.2's existing-install conversion. "
            "Seeding `complete` here asserts a condition this code never established."
        )


class TestMigrationCannotProduceTheForbiddenCell:
    def test_enabled_install_is_left_without_a_cause(self, migration, tmp_path):
        """The case that made the empty-string option unsafe.

        A .env already carrying PARZIVAL_ENABLED=true: the value key is skipped as
        present, so anything appended for the cause lands beside a live `true`.
        """
        env_path = tmp_path / ".env"
        env_path.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        assert migration.update_env_file(dry_run=False) is True

        text = env_path.read_text(encoding="utf-8")
        assert (
            "PARZIVAL_ENABLED_CAUSE" not in text
        ), f"migration appended a cause beside an enabled flag:\n{text}"
        assert "PARZIVAL_ENABLED_CONDITION" not in text, text

    def test_fresh_install_gets_the_value_only(self, migration, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text("UNRELATED=1\n", encoding="utf-8")

        assert migration.update_env_file(dry_run=False) is True

        lines = env_path.read_text(encoding="utf-8").splitlines()
        assert "PARZIVAL_ENABLED=false" in lines, lines
        assert not any(
            line.startswith("PARZIVAL_ENABLED_CAUSE") for line in lines
        ), lines
        assert not any(
            line.startswith("PARZIVAL_ENABLED_CONDITION") for line in lines
        ), lines


class TestAbsentCauseReadsAsUnknown:
    def test_the_state_the_migration_leaves_resolves_to_unknown(self):
        """Rule 4's fail-closed answer, asserted on the value the migration leaves.

        This is the pair to the migration change: with nothing seeded, the entire
        read-side contract rests on absent resolving to `unknown` rather than to
        `opt-out`. Asserted directly rather than only end-to-end.
        """
        assert normalize_cause(None) == "unknown"
        assert normalize_cause("") == "unknown"
