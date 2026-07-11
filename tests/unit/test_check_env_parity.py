"""BP-185 Gate-3 doctor: taxonomy classification, secret-redaction, exit codes.

The doctor (scripts/verify/check_env_parity.py) lives outside the importable
package roots, so it is loaded by file path here.

SECURITY: fixtures use only fake placeholder secret values (``sk-test-*``); a
dedicated test asserts no secret VALUE ever reaches stdout or the JSON output.
"""

import importlib.util
import json

import check_env_completeness as cec

# Load the doctor module by path (scripts/verify/ is not on sys.path).
_DOCTOR_PATH = cec._repo_root / "scripts" / "verify" / "check_env_parity.py"
_spec = importlib.util.spec_from_file_location("check_env_parity", _DOCTOR_PATH)
check_env_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_env_parity)

build_report = check_env_parity.build_report
doctor_main = check_env_parity.main

# Fake secret values — MUST never surface in output.
FAKE_ENV_SECRET = "sk-test-REDACTED-MISPLACED"
FAKE_SECRETS_FILE_SECRET = "sk-test-REDACTED-PROPER"


def _write_scenario(tmp_path):
    """Build an example + deployed env dir exercising every reachable class."""
    example = tmp_path / ".env.example"
    example.write_text(
        "# TOKEN_BUDGET=4000\n"  # commented, schema -> COMMENTED_DOCUMENTED
        "QDRANT_PORT=26350\n",
        encoding="utf-8",
    )

    install = tmp_path / "install"
    docker = install / "docker"
    docker.mkdir(parents=True)
    (docker / ".env").write_text(
        "QDRANT_PORT=26350\n"  # matches default -> PRESENT_OK
        "SIMILARITY_THRESHOLD=0.9\n"  # schema float default 0.7 -> VALUE_DRIFT
        f"GITHUB_TOKEN={FAKE_ENV_SECRET}\n"  # secret in .env -> SECRET_MISPLACED
        "PARZIVAL_USER_NAME=changeme\n"  # placeholder -> PLACEHOLDER_RESIDUE
        "TOTALLY_UNKNOWN_KEY=1\n"  # not schema/example -> ORPHAN_UNKNOWN
        "QDRANT_HOST=localhost # note\n"  # inline comment -> INLINE_COMMENT_HAZARD
        "MAX_RETRIEVALS=10\n"
        "MAX_RETRIEVALS=10\n",  # repeated -> DUPLICATE
        encoding="utf-8",
    )
    (docker / ".env.secrets").write_text(
        f"JIRA_API_TOKEN={FAKE_SECRETS_FILE_SECRET}\n",  # correct placement
        encoding="utf-8",
    )
    return example, install


def _class_map(report):
    return {f["key"]: f["classification"] for f in report["findings"]}


class TestTaxonomyClassification:
    def test_each_class_assigned_correctly(self, tmp_path):
        example, install = _write_scenario(tmp_path)
        classes = _class_map(build_report(example, install))

        assert classes["QDRANT_PORT"] == "PRESENT_OK"
        assert classes["SIMILARITY_THRESHOLD"] == "VALUE_DRIFT_FROM_DEFAULT"
        assert classes["GITHUB_TOKEN"] == "SECRET_MISPLACED"
        assert classes["PARZIVAL_USER_NAME"] == "PLACEHOLDER_RESIDUE"
        assert classes["TOTALLY_UNKNOWN_KEY"] == "ORPHAN_UNKNOWN"
        assert classes["QDRANT_HOST"] == "INLINE_COMMENT_HAZARD"
        assert classes["MAX_RETRIEVALS"] == "DUPLICATE"
        assert classes["JIRA_API_TOKEN"] == "PRESENT_OK"
        assert classes["TOKEN_BUDGET"] == "COMMENTED_DOCUMENTED"
        # A schema field neither deployed nor documented -> optional/defaulted.
        assert classes["DEDUP_THRESHOLD"] == "MISSING_OPTIONAL_DEFAULTED"

    def test_every_key_has_exactly_one_class(self, tmp_path):
        example, install = _write_scenario(tmp_path)
        findings = build_report(example, install)["findings"]
        keys = [f["key"] for f in findings]
        assert len(keys) == len(set(keys)), "each key classified exactly once"

    def test_secret_in_both_env_and_secrets_is_misplaced(self, tmp_path):
        """BP-185 D8 is UNCONDITIONAL: a non-empty secret value in docker/.env is
        SECRET_MISPLACED even when the same key ALSO exists in .env.secrets (the
        'pasted into .env, later added to .env.secrets without removing the first
        copy' mistake). The .env copy is still a cleartext exposure.
        """
        example = tmp_path / ".env.example"
        example.write_text("# TOKEN_BUDGET=4000\n", encoding="utf-8")
        docker = tmp_path / "install" / "docker"
        docker.mkdir(parents=True)
        # Same secret key present, non-empty, in BOTH files.
        (docker / ".env").write_text(
            f"GITHUB_TOKEN={FAKE_ENV_SECRET}\n", encoding="utf-8"
        )
        (docker / ".env.secrets").write_text(
            f"GITHUB_TOKEN={FAKE_SECRETS_FILE_SECRET}\n", encoding="utf-8"
        )

        report = build_report(example, tmp_path / "install")
        classes = _class_map(report)
        severities = {f["key"]: f["severity"] for f in report["findings"]}
        assert classes["GITHUB_TOKEN"] == "SECRET_MISPLACED"
        assert severities["GITHUB_TOKEN"] == "ERROR"

        rc = doctor_main(
            [
                "--install-dir",
                str(tmp_path / "install"),
                "--env-example",
                str(example),
            ]
        )
        assert rc == 1


class TestSecretRedaction:
    def test_no_secret_value_in_json_or_human_output(self, tmp_path, capsys):
        example, install = _write_scenario(tmp_path)
        args = ["--install-dir", str(install), "--env-example", str(example)]

        doctor_main([*args, "--json"])
        json_out = capsys.readouterr().out
        assert FAKE_ENV_SECRET not in json_out
        assert FAKE_SECRETS_FILE_SECRET not in json_out

        doctor_main(args)
        human_out = capsys.readouterr().out
        assert FAKE_ENV_SECRET not in human_out
        assert FAKE_SECRETS_FILE_SECRET not in human_out
        # ...but the key NAMES are still reported.
        assert "GITHUB_TOKEN" in human_out
        assert "JIRA_API_TOKEN" in human_out


class TestJsonShape:
    def test_json_report_structure(self, tmp_path, capsys):
        example, install = _write_scenario(tmp_path)
        doctor_main(
            ["--install-dir", str(install), "--env-example", str(example), "--json"]
        )
        report = json.loads(capsys.readouterr().out)

        assert set(report) >= {
            "install_dir",
            "deployed_env_found",
            "error_count",
            "summary",
            "findings",
        }
        assert report["deployed_env_found"] is True
        assert set(report["summary"]) == {"by_class", "by_severity"}
        for finding in report["findings"]:
            assert set(finding) == {"key", "classification", "severity"}


class TestExitCodes:
    def test_error_class_findings_exit_1(self, tmp_path):
        example, install = _write_scenario(tmp_path)
        rc = doctor_main(["--install-dir", str(install), "--env-example", str(example)])
        assert rc == 1

    def test_clean_deployment_exits_0(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text("# TOKEN_BUDGET=4000\n", encoding="utf-8")
        docker = tmp_path / "install" / "docker"
        docker.mkdir(parents=True)
        (docker / ".env").write_text("QDRANT_PORT=26350\n", encoding="utf-8")
        (docker / ".env.secrets").write_text("", encoding="utf-8")

        rc = doctor_main(
            ["--install-dir", str(tmp_path / "install"), "--env-example", str(example)]
        )
        assert rc == 0

    def test_missing_deployed_env_degrades_gracefully(self, tmp_path, capsys):
        example = tmp_path / ".env.example"
        example.write_text("# TOKEN_BUDGET=4000\n", encoding="utf-8")
        empty_install = tmp_path / "nope"  # no docker/.env at all

        rc = doctor_main(
            ["--install-dir", str(empty_install), "--env-example", str(example)]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "deployed env not found" in out

    def test_absent_deployed_env_exit_0_even_with_required_field(
        self, tmp_path, monkeypatch
    ):
        """When the deployed env is entirely absent, a required schema field must
        NOT count as MISSING_REQUIRED / exit 1 — that would contradict the human
        output's 'classifying schema vs example only' graceful message. Injects a
        synthetic required field (the live schema has none) to exercise the path.
        """
        from pydantic.fields import FieldInfo

        patched = dict(check_env_parity.MemoryConfig.model_fields)
        patched["FORCED_REQUIRED_TESTONLY"] = FieldInfo(annotation=str)
        monkeypatch.setattr(check_env_parity.MemoryConfig, "model_fields", patched)

        example = tmp_path / ".env.example"
        example.write_text("# TOKEN_BUDGET=4000\n", encoding="utf-8")
        empty_install = tmp_path / "nope"  # no docker/.env at all

        report = build_report(example, empty_install)
        classes = _class_map(report)
        assert classes["FORCED_REQUIRED_TESTONLY"] != "MISSING_REQUIRED"

        rc = doctor_main(
            ["--install-dir", str(empty_install), "--env-example", str(example)]
        )
        assert rc == 0
