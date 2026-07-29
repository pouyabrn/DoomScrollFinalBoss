# Automation rules

- Production secrets are available only to `schedule` and manually dispatched jobs on the default branch.
- Never use `pull_request_target` with secret-bearing steps.
- Keep workflow permissions at `contents: read` unless a documented feature needs more.
- Pin every Action to a full commit SHA; Dependabot may update the pin.
- Never upload production HTML, plain text, database dumps, prompts, raw provider responses, or logs containing private URLs.
- Keep `concurrency.cancel-in-progress` false for delivery so a newer run cannot kill a send mid-flight.
- Database migration and strict doctor checks run before delivery.
