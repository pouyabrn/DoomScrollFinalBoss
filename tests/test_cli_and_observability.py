import json
import logging
from pathlib import Path

import pytest

from finalboss.cli import main
from finalboss.observability import JsonFormatter, configure_logging


def test_doctor_reports_presence_without_secret_values(
    tmp_path: Path,
    monkeypatch: object,
    capsys: object,
) -> None:
    setenv = monkeypatch.setenv
    setenv("FINALBOSS_DATABASE_URL", f"sqlite:///{tmp_path / 'doctor.db'}")
    setenv("FINALBOSS_OPENROUTER_API_KEY", "do-not-print-openrouter")
    setenv("FINALBOSS_RESEND_API_KEY", "do-not-print-resend")
    setenv("FINALBOSS_EMAIL_TO", "owner@example.com")
    setenv("FINALBOSS_EMAIL_FROM", "Digest <digest@example.com>")
    setenv("FINALBOSS_PRIVACY_KEY", "x" * 32)
    assert main(["doctor", "--strict"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["ready"] is True
    assert "do-not-print" not in output
    assert "owner@example.com" not in output


def test_json_logging_contains_safe_structured_fields() -> None:
    configure_logging("INFO")
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "source_complete",
        (),
        None,
    )
    record.source_id = "openai"
    payload = json.loads(formatter.format(record))
    assert payload["event"] == "source_complete"
    assert payload["source_id"] == "openai"


def test_delivery_only_doctor_does_not_require_editor_credentials(
    tmp_path: Path,
    monkeypatch: object,
    capsys: object,
) -> None:
    setenv = monkeypatch.setenv
    setenv("FINALBOSS_DATABASE_URL", f"sqlite:///{tmp_path / 'delivery-doctor.db'}")
    setenv("FINALBOSS_RESEND_API_KEY", "do-not-print-resend")
    setenv("FINALBOSS_EMAIL_TO", "owner@example.com")
    setenv("FINALBOSS_EMAIL_FROM", "Digest <digest@example.com>")
    setenv("FINALBOSS_PRIVACY_KEY", "x" * 32)
    assert main(["doctor", "--delivery-only"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["openrouter_key"] is False
    assert payload["ready"] is True


def test_force_resend_cannot_be_a_dry_run() -> None:
    with pytest.raises(SystemExit, match="cannot be combined"):
        main(["run", "--dry-run", "--force-resend"])
