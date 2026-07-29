import re
from pathlib import Path

_FULL_COMMIT_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def test_every_action_is_pinned_to_a_full_commit() -> None:
    workflows = Path(".github/workflows").glob("*.yml")
    references: list[str] = []
    for workflow in workflows:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                references.append(stripped.removeprefix("uses:").split(maxsplit=1)[0])
    assert references
    assert all(_FULL_COMMIT_PIN.fullmatch(reference) for reference in references)


def test_delivery_workflow_keeps_secrets_out_of_job_scope() -> None:
    workflow = Path(".github/workflows/daily-digest.yml").read_text(encoding="utf-8")
    job_prefix, steps = workflow.split("    steps:", maxsplit=1)
    assert "secrets." not in job_prefix
    assert "pull_request_target" not in workflow
    assert "actions/upload-artifact" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert (
        "FINALBOSS_OPENROUTER_API_KEY"
        not in steps.split("- name: Force resend today's stored digest", maxsplit=1)[1]
    )
