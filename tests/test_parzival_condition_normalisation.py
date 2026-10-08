"""The condition axis of the Parzival enablement record normalises like the cause.

Story 1.2 Task 7 / AC-4. The record carries three keys, and until this story only
two of them had a reader that normalised. ``PARZIVAL_ENABLED_CONDITION`` had
none. That was harmless while ``partial`` was unreachable -- every write passed
two arguments and so recorded the default -- and Task 4 is what makes it
reachable, which is what makes the gap load-bearing.

The failure direction is the dangerous one: a raw comparison against the literal
``partial`` is false for ``Partial``, for a quoted value and for a CRLF
``docker/.env``, so a partial install reads as complete on the transport that has
not been through python-dotenv.

THREE TRANSPORTS, and the record must survive all of them or AC-3/AC-4 are
satisfied on one and false on the others (BUG-120 is recorded as exactly this
class): the raw ``docker/.env`` text, ``settings.json`` -> process env, and the
``MemoryConfig`` attribute.
"""

import pytest

from memory.config import (
    CONDITION_COMPLETE,
    CONDITION_PARTIAL,
    normalize_condition,
    resolve_condition,
    resolve_condition_from_env,
)
from memory.parzival_state import normalize_cause


class _FakeConfig:
    def __init__(self, condition):
        self.parzival_enabled_condition = condition


class TestPartialSurvivesEveryTransport:
    """Item 11: assert ``partial`` round-trips, now that Task 4 makes it reachable."""

    def test_transport_2_raw_process_env(self):
        assert (
            resolve_condition_from_env({"PARZIVAL_ENABLED_CONDITION": "partial"})
            == CONDITION_PARTIAL
        )

    def test_transport_3_memory_config_attribute(self):
        assert resolve_condition(_FakeConfig("partial")) == CONDITION_PARTIAL

    @pytest.mark.parametrize(
        "raw",
        [
            "partial",
            "Partial",
            "PARTIAL",
            " partial ",
            '"partial"',
            "'partial'",
            "partial\r",
            ' "Partial" \r',
        ],
        ids=[
            "bare",
            "title-case",
            "upper",
            "whitespace",
            "double-quoted",
            "single-quoted",
            "crlf",
            "all-at-once",
        ],
    )
    def test_every_shape_the_untransformed_transport_can_deliver(self, raw):
        """python-dotenv strips quotes and the CR before MemoryConfig sees them;
        raw process env is where nothing has. Each of these is false against a
        literal ``== "partial"`` comparison, which is what "no normalisation
        counterpart" meant in practice.
        """
        assert normalize_condition(raw) == CONDITION_PARTIAL


class TestTheAbsentAndUnreadableCases:
    def test_an_absent_condition_means_complete(self):
        """Every install predating this record carries no condition key: both
        .env.example merge loops append only missing keys.
        """
        assert normalize_condition(None) == CONDITION_COMPLETE
        assert resolve_condition_from_env({}) == CONDITION_COMPLETE

    def test_an_empty_condition_means_complete(self):
        assert normalize_condition("") == CONDITION_COMPLETE

    def test_an_unrecognised_token_resolves_to_complete(self):
        """Pinned as a decision, not as an accident. Reading a typo as ``partial``
        would be the safer-sounding direction, but ``partial`` is a claim that a
        deployment stopped part-way and a garbled token is no evidence of one.
        A third state meaning "unreadable" would be a Condition Table entry,
        which AD-24 assigns to the spine.
        """
        assert normalize_condition("partail") == CONDITION_COMPLETE
        assert normalize_condition("banana") == CONDITION_COMPLETE

    def test_a_non_string_raises_rather_than_coercing(self):
        """A MagicMock(spec=MemoryConfig) that never assigns the attribute still
        auto-creates one, and spec= constrains names rather than values. Silent
        coercion would let the condition branch take the wrong path with the
        tests still green.
        """
        with pytest.raises(TypeError):
            normalize_condition(object())


class TestTheTwoNormalisersAgree:
    """One record, one transform. Two normalisers for the same file that differ
    in any step are a reader-disagreement bug waiting to happen -- which is the
    defect class the cause axis already carries an equivalence test for.
    """

    @pytest.mark.parametrize(
        "raw",
        ["x", " x ", '"x"', "'x'", "x\r", ' "X" \r', "", "   "],
    )
    def test_the_transform_is_character_for_character_the_cause_transform(self, raw):
        """Compared through a token each normaliser treats as unknown, so what is
        being compared is the strip/lower transform itself rather than either
        one's fail-closed default.
        """
        cause_shape = normalize_cause(raw.replace("x", "failed").replace("X", "FAILED"))
        condition_shape = normalize_condition(
            raw.replace("x", "partial").replace("X", "PARTIAL")
        )
        assert (cause_shape == "failed") == (condition_shape == CONDITION_PARTIAL), (
            f"the two normalisers disagree on {raw!r}: "
            f"cause -> {cause_shape}, condition -> {condition_shape}"
        )
