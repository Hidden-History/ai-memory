"""Contract tests for aim-sot registry schema (SOT Wave-1 Item 1).

Covers:
  S1  — schema file is valid JSON and loads cleanly
  S2  — a valid minimal entry (6 core fields only) passes validation
  S3  — a valid full entry (all defined fields) passes validation
  S4  — missing each of the 6 core required fields causes validation failure
  S5  — kind value outside the 8-enum fails
  S6  — boundary_type value outside the 3-enum fails
  S7  — status value outside the 3-enum fails
  S8  — registry.yaml.template parses as YAML and validates clean against the schema
  S9  — no-auto-bump rule: schema does not define machine hash / timestamp / drift fields
  S10 — additionalProperties:false actually rejects unknown fields at instance level
        (entry-level and document-level)

All tests are hermetic (no network calls, no filesystem side-effects beyond reads).
"""

import json
from pathlib import Path

import pytest
import yaml

try:
    from jsonschema import Draft7Validator, FormatChecker, ValidationError

    _JSONSCHEMA_OK = True
except ImportError:  # pragma: no cover
    _JSONSCHEMA_OK = False

pytestmark = pytest.mark.skipif(not _JSONSCHEMA_OK, reason="jsonschema not installed")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SKILL_ROOT = Path(__file__).resolve().parents[1] / "_ai-memory" / "skills" / "aim-sot"
SCHEMA_FILE = SKILL_ROOT / "schema" / "registry.schema.json"
TEMPLATE_FILE = SKILL_ROOT / "templates" / "registry.yaml.template"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_schema():
    return json.loads(SCHEMA_FILE.read_text())


def _validate(instance, schema=None):
    """Validate *instance* against the registry schema.

    Returns None on success, raises jsonschema.ValidationError on failure.
    """
    if schema is None:
        schema = _load_schema()
    Draft7Validator(schema, format_checker=FormatChecker()).validate(instance)


def _valid_entry(**overrides):
    """Return a minimal valid registry entry (all 6 core fields present)."""
    entry = {
        "id": "example-service",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/services/example",
        "owner": "@example-team",
        "description": "The example service handles authentication.",
    }
    entry.update(overrides)
    return entry


def _valid_registry(entries=None):
    """Return a minimal valid registry document."""
    return {
        "schema_version": "1.0",
        "entries": entries if entries is not None else [_valid_entry()],
    }


# ---------------------------------------------------------------------------
# S1 — schema file is valid JSON and loads cleanly
# ---------------------------------------------------------------------------


def test_S1_schema_loads():
    assert SCHEMA_FILE.exists(), f"schema file missing: {SCHEMA_FILE}"
    schema = _load_schema()
    assert isinstance(schema, dict)
    assert "$schema" in schema
    assert "definitions" in schema
    assert "entry" in schema["definitions"]
    # Top-level required fields declared
    assert set(schema["required"]) == {"schema_version", "entries"}


# ---------------------------------------------------------------------------
# S2 — valid minimal entry passes
# ---------------------------------------------------------------------------


def test_S2_valid_minimal_entry_passes():
    _validate(_valid_registry())


# ---------------------------------------------------------------------------
# S3 — valid full entry (all defined fields) passes
# ---------------------------------------------------------------------------


def test_S3_valid_full_entry_passes():
    entry = _valid_entry(
        last_verified="2024-06-01",
        added_by="@alice",
        provenance_note="Added via aim-sot detect-propose.",
        status="active",
        source_repo="https://github.com/org/repo",
        docs_url="https://docs.example.com/service",
        api_spec="openapi/service.yaml",
        ci_url="https://ci.example.com/service",
        runbook_url="https://runbooks.example.com/service",
        dashboard_url="https://grafana.example.com/d/service",
        adr_dir="docs/decisions/service",
        drift_check="python tools/check_service.py",
        links=[
            {
                "name": "Slack channel",
                "url": "https://slack.example.com/service",
                "type": "chat",
            },
        ],
    )
    _validate(_valid_registry([entry]))


# ---------------------------------------------------------------------------
# S4 — missing each core required field causes validation failure
# ---------------------------------------------------------------------------

CORE_REQUIRED_FIELDS = [
    "id",
    "kind",
    "boundary_type",
    "sot_location",
    "owner",
    "description",
]


@pytest.mark.parametrize("field", CORE_REQUIRED_FIELDS)
def test_S4_missing_core_field_fails(field):
    entry = _valid_entry()
    del entry[field]
    with pytest.raises(ValidationError):
        _validate(_valid_registry([entry]))


# ---------------------------------------------------------------------------
# S5 — kind outside the 8-enum fails
# ---------------------------------------------------------------------------


def test_S5_kind_invalid_fails():
    entry = _valid_entry(kind="microservice")  # not in the enum
    with pytest.raises(ValidationError):
        _validate(_valid_registry([entry]))


def test_S5_kind_all_valid_values_pass():
    kinds = [
        "service",
        "library",
        "application",
        "api",
        "data",
        "infrastructure",
        "decision",
        "documentation",
    ]
    for kind in kinds:
        _validate(_valid_registry([_valid_entry(kind=kind)]))


# ---------------------------------------------------------------------------
# S6 — boundary_type outside the 3-enum fails
# ---------------------------------------------------------------------------


def test_S6_boundary_type_invalid_fails():
    entry = _valid_entry(boundary_type="module")  # not in the enum
    with pytest.raises(ValidationError):
        _validate(_valid_registry([entry]))


def test_S6_boundary_type_all_valid_values_pass():
    for bt in ["path", "component", "concern"]:
        _validate(_valid_registry([_valid_entry(boundary_type=bt)]))


# ---------------------------------------------------------------------------
# S7 — status outside the 3-enum fails
# ---------------------------------------------------------------------------


def test_S7_status_invalid_fails():
    entry = _valid_entry(status="deprecated")  # not in the enum
    with pytest.raises(ValidationError):
        _validate(_valid_registry([entry]))


def test_S7_status_all_valid_values_pass():
    for status in ["proposed", "active", "superseded"]:
        _validate(_valid_registry([_valid_entry(status=status)]))


# ---------------------------------------------------------------------------
# S8 — registry.yaml.template parses as YAML and validates clean
# ---------------------------------------------------------------------------


def test_S8_template_parses_as_yaml():
    assert TEMPLATE_FILE.exists(), f"template missing: {TEMPLATE_FILE}"
    content = TEMPLATE_FILE.read_text()
    doc = yaml.safe_load(content)
    assert isinstance(doc, dict), "template did not parse to a dict"
    assert "schema_version" in doc
    assert "entries" in doc
    assert isinstance(doc["entries"], list)


def test_S8_template_validates_against_schema():
    """The template, once parsed, must be a valid registry instance.

    Dates in the template are quoted strings (e.g. "2024-01-15") so they round-trip
    through PyYAML as strings and satisfy the schema's 'format: date' constraint.
    """
    doc = yaml.safe_load(TEMPLATE_FILE.read_text())
    _validate(doc)


def test_S8_template_has_example_entries():
    doc = yaml.safe_load(TEMPLATE_FILE.read_text())
    entries = doc.get("entries", [])
    assert len(entries) >= 1, "template should have at least one example entry"
    # Example entries must have all 6 core fields
    for entry in entries:
        for field in CORE_REQUIRED_FIELDS:
            assert field in entry, f"example entry missing core field: {field}"


# ---------------------------------------------------------------------------
# S9 — no-auto-bump rule: forbidden machine fields absent from schema definition
# ---------------------------------------------------------------------------

# Fields that must NOT appear in the schema's entry properties — they belong in
# the per-install drift cache, never in the human-committed registry.
FORBIDDEN_MACHINE_FIELDS = [
    "content_hash",
    "drift_status",
    "last_verified_at",
    "last_verified_sha",
    "machine_timestamp",
    "upstream_sha",
    "installed_sha",
    "upstream_repo",
]


def test_S9_no_machine_fields_in_entry_schema():
    schema = _load_schema()
    entry_props = schema["definitions"]["entry"].get("properties", {})
    for field in FORBIDDEN_MACHINE_FIELDS:
        assert field not in entry_props, (
            f"Machine field '{field}' must not be defined in the entry schema — "
            f"it belongs in the per-install drift cache, not the committed registry."
        )


def test_S9_no_machine_fields_required():
    schema = _load_schema()
    entry_required = schema["definitions"]["entry"].get("required", [])
    for field in FORBIDDEN_MACHINE_FIELDS:
        assert (
            field not in entry_required
        ), f"Machine field '{field}' must not be in entry 'required'."


def test_S9_schema_version_is_not_machine_generated():
    """schema_version is a human-set string, not a machine-auto-bumped hash or timestamp."""
    schema = _load_schema()
    sv_prop = schema["properties"]["schema_version"]
    assert sv_prop["type"] == "string"
    # Must NOT be type 'integer' or define a 'format' that implies auto-generation
    assert sv_prop.get("format") not in (
        "date-time",
        "uri",
    ), "schema_version must not use a machine-timestamp or hash format"


# ---------------------------------------------------------------------------
# S10 — additionalProperties:false enforced at instance level (structural lock)
# ---------------------------------------------------------------------------


def test_S10_unknown_field_on_entry_rejected():
    """additionalProperties:false on the entry definition must reject any unknown field
    at validation time — not just at schema-inspection time. Dropping the keyword would
    keep S9 green but break this test."""
    entry = _valid_entry(content_hash="abc123")  # machine field injected
    with pytest.raises(ValidationError):
        _validate(_valid_registry([entry]))


def test_S10_unknown_field_on_document_rejected():
    """additionalProperties:false on the top-level document object must reject unknown
    fields at the document level too."""
    doc = _valid_registry()
    doc["drift_status"] = "clean"  # top-level unknown field injected
    with pytest.raises(ValidationError):
        _validate(doc)
