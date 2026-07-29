import json
import logging
from pathlib import Path

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
