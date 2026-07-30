from __future__ import annotations

import hashlib
from datetime import date

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from premailer import transform

from finalboss.models import Digest, DigestItem, RenderedDigest
from finalboss.processing.normalize import clean_text

_ACCENTS = (
    ("signal-yellow", "#FFF000"),
    ("vector-green", "#00E56B"),
    ("relay-pink", "#FF4FA0"),
    ("terminal-blue", "#3D7CFF"),
)


class DigestRenderer:
    def __init__(self) -> None:
        self._environment = Environment(
            loader=PackageLoader("finalboss.email"),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, digest: Digest, *, subject_prefix: str) -> RenderedDigest:
        digest = _sanitize_for_html_parser(digest)
        subject = f"{subject_prefix} · {digest.edition_date.isoformat()}"
        accent_name, accent = _edition_accent(digest.edition_date)
        evidence_ids = set(digest.linkedin_opportunity.evidence_item_ids)
        context = {
            "digest": digest,
            "linkedin_evidence": [item for item in digest.items if item.story.id in evidence_ids],
            "healthy_count": sum(status.ok for status in digest.source_statuses),
            "source_count": len(digest.source_statuses),
            "accent_name": accent_name,
            "accent": accent,
            "edition_number": digest.edition_date.strftime("%j"),
            "edition_code": _edition_code(digest.edition_date),
        }
        raw_html = self._environment.get_template("digest.html.j2").render(**context)
        html = transform(
            raw_html,
            disable_link_rewrites=True,
            remove_classes=False,
            strip_important=False,
        )
        text = self._environment.get_template("digest.txt.j2").render(**context)
        return RenderedDigest(subject=subject, html=html, text=text.strip())


def _sanitize_for_html_parser(digest: Digest) -> Digest:
    """Strip markup before Premailer's HTML parser can reinterpret escaped entities."""
    items = [
        DigestItem(
            position=item.position,
            story=item.story.model_copy(
                update={
                    "title": clean_text(item.story.title, limit=500),
                    "source_name": clean_text(item.story.source_name, limit=100),
                }
            ),
            editorial=item.editorial.model_copy(
                update={
                    "eli5": clean_text(item.editorial.eli5, limit=500),
                    "why_it_matters": clean_text(item.editorial.why_it_matters, limit=300),
                    "uncertainty": clean_text(item.editorial.uncertainty, limit=180),
                    "category": clean_text(item.editorial.category, limit=40),
                }
            ),
            final_score=item.final_score,
        )
        for item in digest.items
    ]
    return digest.model_copy(
        update={
            "title": clean_text(digest.title, limit=100),
            "subtitle": clean_text(digest.subtitle, limit=200),
            "items": items,
            "forecast_lines": [clean_text(line, limit=240) for line in digest.forecast_lines],
            "linkedin_opportunity": digest.linkedin_opportunity.model_copy(
                update={
                    "topic": clean_text(digest.linkedin_opportunity.topic, limit=160),
                    "post_lines": [
                        clean_text(line, limit=420)
                        for line in digest.linkedin_opportunity.post_lines
                    ],
                    "why_now": clean_text(digest.linkedin_opportunity.why_now, limit=300),
                }
            ),
        }
    )


def _edition_accent(edition_date: date) -> tuple[str, str]:
    """Choose a stable, random-looking accent so retries render identically."""
    digest = hashlib.sha256(edition_date.isoformat().encode()).digest()
    return _ACCENTS[digest[0] % len(_ACCENTS)]


def _edition_code(edition_date: date) -> str:
    digest = hashlib.sha256(f"finalboss:{edition_date.isoformat()}".encode()).hexdigest()
    return digest[:8].upper()
