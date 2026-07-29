from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from finalboss.models import Digest, RenderedDigest
from finalboss.processing.normalize import fingerprint


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    collected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    digest_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded_sources: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(100))


class DigestRecord(Base):
    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("edition_date", "recipient_hmac", name="uq_digest_recipient_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    edition_date: Mapped[date] = mapped_column(Date, nullable=False)
    recipient_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    error_category: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[DigestItemRecord]] = relationship(
        back_populates="digest", cascade="all, delete-orphan"
    )


class DigestItemRecord(Base):
    __tablename__ = "digest_items"
    __table_args__ = (UniqueConstraint("digest_id", "position", name="uq_digest_position"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    digest_id: Mapped[str] = mapped_column(ForeignKey("digests.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    story_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[DigestRecord] = relationship(back_populates="items")


@dataclass(frozen=True)
class StoredDigest:
    id: str
    edition_date: date
    status: str
    rendered: RenderedDigest
    provider_message_id: str | None


def recipient_fingerprint(email: str, privacy_key: str) -> str:
    return hmac.digest(
        privacy_key.encode(),
        email.strip().lower().encode(),
        "sha256",
    ).hex()


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Database:
    def __init__(self, url: str) -> None:
        normalized = _normalize_database_url(url)
        if normalized.startswith("sqlite:///"):
            path = Path(normalized.removeprefix("sqlite:///"))
            if path != Path(":memory:"):
                path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(
            normalized,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self, *, allow_create: bool) -> None:
        if allow_create:
            Base.metadata.create_all(self._engine)
            return
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM digests LIMIT 1"))
        except OperationalError as exc:
            raise RuntimeError(
                "database schema is unavailable; run `alembic upgrade head` first"
            ) from exc

    def ping(self) -> None:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def begin_run(self) -> str:
        run_id = str(uuid.uuid4())
        with self._sessions.begin() as session:
            session.add(
                RunRecord(
                    id=run_id,
                    started_at=datetime.now(UTC),
                    status="running",
                )
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        collected_count: int,
        digest_count: int,
        degraded_sources: int,
        error_category: str | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return
            record.finished_at = datetime.now(UTC)
            record.status = status
            record.collected_count = collected_count
            record.digest_count = digest_count
            record.degraded_sources = degraded_sources
            record.error_category = error_category

    def get_digest(self, *, edition_date: date, recipient_hmac: str) -> StoredDigest | None:
        with self._sessions() as session:
            record = session.scalar(
                select(DigestRecord).where(
                    DigestRecord.edition_date == edition_date,
                    DigestRecord.recipient_hmac == recipient_hmac,
                )
            )
            return _to_stored(record) if record is not None else None

    def save_pending_digest(
        self,
        *,
        digest: Digest,
        rendered: RenderedDigest,
        recipient_hmac: str,
    ) -> StoredDigest:
        digest_id = str(uuid.uuid4())
        record = DigestRecord(
            id=digest_id,
            edition_date=digest.edition_date,
            recipient_hmac=recipient_hmac,
            status="pending",
            subject=rendered.subject,
            html=rendered.html,
            text=rendered.text,
            model=digest.model,
            prompt_version=digest.prompt_version,
            created_at=datetime.now(UTC),
            items=[
                DigestItemRecord(
                    position=item.position,
                    story_fingerprint=fingerprint(item.story.canonical_url, item.story.title),
                    source_id=item.story.source_id,
                    canonical_url=item.story.canonical_url,
                )
                for item in digest.items
            ],
        )
        try:
            with self._sessions.begin() as session:
                session.add(record)
            return _to_stored(record)
        except IntegrityError:
            existing = self.get_digest(
                edition_date=digest.edition_date,
                recipient_hmac=recipient_hmac,
            )
            if existing is None:
                raise
            return existing

    def mark_sent(self, digest_id: str, provider_message_id: str) -> None:
        with self._sessions.begin() as session:
            record = session.get(DigestRecord, digest_id)
            if record is None:
                raise ValueError("digest ledger record is missing")
            record.status = "sent"
            record.provider_message_id = provider_message_id
            record.sent_at = datetime.now(UTC)
            record.error_category = None

    def mark_failed(self, digest_id: str, error_category: str) -> None:
        with self._sessions.begin() as session:
            record = session.get(DigestRecord, digest_id)
            if record is None:
                return
            record.status = "failed"
            record.error_category = error_category[:100]

    def recent_story_fingerprints(self, *, days: int = 30) -> set[str]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self._sessions() as session:
            rows = session.scalars(
                select(DigestItemRecord.story_fingerprint)
                .join(DigestRecord)
                .where(DigestRecord.sent_at >= cutoff)
            )
            return set(rows)

    def close(self) -> None:
        self._engine.dispose()


def _to_stored(record: DigestRecord) -> StoredDigest:
    return StoredDigest(
        id=record.id,
        edition_date=record.edition_date,
        status=record.status,
        rendered=RenderedDigest(
            subject=record.subject,
            html=record.html,
            text=record.text,
        ),
        provider_message_id=record.provider_message_id,
    )
