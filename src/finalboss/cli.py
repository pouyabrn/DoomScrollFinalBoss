from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from finalboss.config import Settings, load_configuration, secret_value
from finalboss.observability import configure_logging
from finalboss.pipeline import DigestPipeline
from finalboss.storage.database import Database


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finalboss",
        description="Private daily AI-news briefing.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="Collect, rank, render, and optionally send.")
    run.add_argument("--dry-run", action="store_true", help="Write an HTML preview; never email.")
    run.add_argument(
        "--force-resend",
        action="store_true",
        help="Resend today's stored digest using a new audited delivery key.",
    )
    run.add_argument(
        "--fixture", type=Path, help="Use a local story fixture instead of the network."
    )
    run.add_argument("--output", type=Path, help="Dry-run HTML output path.")

    doctor = subcommands.add_parser("doctor", help="Validate config, storage, and secret presence.")
    doctor.add_argument(
        "--strict", action="store_true", help="Require production delivery secrets."
    )
    doctor.add_argument(
        "--require-social",
        action="store_true",
        help="Also require approved Reddit and paid X credentials.",
    )
    doctor.add_argument(
        "--delivery-only",
        action="store_true",
        help="Require only the secrets needed to deliver a stored digest.",
    )

    subcommands.add_parser("migrate", help="Upgrade the database schema to the latest revision.")
    return parser


def _doctor(
    settings: Settings,
    *,
    strict: bool,
    require_social: bool,
    delivery_only: bool,
) -> int:
    public, registry = load_configuration(settings)
    checks: dict[str, object] = {
        "configuration": "ok",
        "feeds_configured": len(registry.feeds),
        "openrouter_key": bool(secret_value(settings.openrouter_api_key)),
        "resend_key": bool(secret_value(settings.resend_api_key)),
        "recipient": bool(secret_value(settings.email_to)),
        "sender": bool(secret_value(settings.email_from)),
        "privacy_key": len(secret_value(settings.privacy_key) or "") >= 32,
        "reddit_credentials": bool(
            secret_value(settings.reddit_client_id) and secret_value(settings.reddit_client_secret)
        ),
        "x_credentials": bool(secret_value(settings.x_bearer_token)),
        "timezone": public.newsletter.timezone,
        "llm_model": public.llm.model,
    }
    database_url = secret_value(settings.database_url)
    database_ok = False
    if database_url:
        try:
            database = Database(database_url)
            database.initialize(allow_create=settings.environment != "production")
            database.ping()
            database.close()
            database_ok = True
        except Exception:
            database_ok = False
    checks["database"] = "ok" if database_ok else "failed"

    required: list[str] = []
    if delivery_only:
        required.extend(["resend_key", "recipient", "sender", "privacy_key"])
    elif strict:
        required.extend(["openrouter_key", "resend_key", "recipient", "sender", "privacy_key"])
    if require_social and not delivery_only:
        required.extend(["reddit_credentials", "x_credentials"])
    failed = not database_ok or any(not checks[key] for key in required)
    checks["ready"] = not failed
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)
    if args.command == "doctor":
        return _doctor(
            settings,
            strict=args.strict,
            require_social=args.require_social,
            delivery_only=args.delivery_only,
        )
    if args.command == "migrate":
        command.upgrade(AlembicConfig("alembic.ini"), "head")
        return 0
    if args.command == "run":
        public, registry = load_configuration(settings)
        if args.dry_run and args.force_resend:
            raise SystemExit("--force-resend cannot be combined with --dry-run")
        if not args.dry_run and args.fixture is not None:
            raise SystemExit("--fixture can only be used with --dry-run")
        summary = asyncio.run(
            DigestPipeline(settings, public, registry).run(
                send=not args.dry_run,
                force_resend=args.force_resend,
                fixture=args.fixture,
                output=args.output,
            )
        )
        # This summary is deliberately free of recipient, body, and source text.
        print(summary.model_dump_json(indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
