from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from src.models import ParsedReceipt


class Base(DeclarativeBase):
    pass


class ReceiptRow(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_message_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    discord_channel_id: Mapped[str] = mapped_column(String, nullable=False)
    discord_user_id: Mapped[str] = mapped_column(String, nullable=False)
    image_path: Mapped[str] = mapped_column(String, nullable=False)
    image_content_type: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    active_version_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    versions: Mapped[list[ReceiptVersionRow]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        primaryjoin="ReceiptRow.id == ReceiptVersionRow.receipt_id",
    )
    items: Mapped[list[ItemRow]] = relationship(back_populates="receipt", cascade="all, delete-orphan")


class ReceiptVersionRow(Base):
    __tablename__ = "receipt_versions"
    __table_args__ = (UniqueConstraint("receipt_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_model_output: Mapped[str | None] = mapped_column(Text)
    correction_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    receipt: Mapped[ReceiptRow] = relationship(back_populates="versions")
    items: Mapped[list[ItemRow]] = relationship(back_populates="version", cascade="all, delete-orphan")


class ItemRow(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[int] = mapped_column(ForeignKey("receipt_versions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str | None] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String)
    unit_price: Mapped[float | None] = mapped_column(Float)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    receipt: Mapped[ReceiptRow] = relationship(back_populates="items")
    version: Mapped[ReceiptVersionRow] = relationship(back_populates="items")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}", future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.migrate()

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_receipt(
        self,
        *,
        discord_message_id: str,
        discord_channel_id: str,
        discord_user_id: str,
        image_path: Path,
        image_content_type: str | None,
    ) -> int:
        with self.session_factory() as session:
            receipt = ReceiptRow(
                discord_message_id=discord_message_id,
                discord_channel_id=discord_channel_id,
                discord_user_id=discord_user_id,
                image_path=str(image_path),
                image_content_type=image_content_type,
                status="pending",
            )
            session.add(receipt)
            session.commit()
            return receipt.id

    def add_version(
        self,
        *,
        receipt_id: int,
        parsed: ParsedReceipt,
        raw_model_output: str | None,
        source: Literal["ai", "user_correction"] = "ai",
        correction_note: str | None = None,
    ) -> int:
        with self.session_factory() as session:
            receipt = self._get_receipt(session, receipt_id)
            latest_version = session.scalar(
                select(func.coalesce(func.max(ReceiptVersionRow.version_number), 0)).where(
                    ReceiptVersionRow.receipt_id == receipt_id
                )
            )
            version = ReceiptVersionRow(
                receipt_id=receipt_id,
                version_number=int(latest_version or 0) + 1,
                source=source,
                status="pending",
                parsed_json=parsed.model_dump_json(),
                raw_model_output=raw_model_output,
                correction_note=correction_note,
            )
            session.add(version)
            session.flush()
            receipt.active_version_id = version.id
            session.commit()
            return version.id

    def approve_version(self, version_id: int) -> None:
        with self.session_factory() as session:
            version = self._get_version(session, version_id)
            receipt = version.receipt
            parsed = ParsedReceipt.model_validate_json(version.parsed_json)

            for existing_version in receipt.versions:
                existing_version.status = "rejected"
            version.status = "approved"
            receipt.status = "approved"
            receipt.active_version_id = version.id
            receipt.approved_at = datetime.now(UTC)
            receipt.items.clear()

            for item in parsed.items:
                session.add(
                    ItemRow(
                        receipt_id=receipt.id,
                        version_id=version.id,
                        name=item.name,
                        original_name=item.original_name,
                        category=item.category.value,
                        quantity=item.quantity,
                        unit=item.unit,
                        unit_price=item.unit_price,
                        total_price=item.total_price,
                        currency=item.currency or parsed.currency,
                        confidence=item.confidence,
                        notes=item.notes,
                    )
                )
            session.commit()

    def reject_receipt(self, version_id: int) -> None:
        with self.session_factory() as session:
            version = self._get_version(session, version_id)
            version.status = "rejected"
            version.receipt.status = "rejected"
            version.receipt.rejected_at = datetime.now(UTC)
            session.commit()

    def approved_items_for_csv(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(
                select(ReceiptRow, ReceiptVersionRow, ItemRow)
                .join(ReceiptVersionRow, ReceiptVersionRow.id == ItemRow.version_id)
                .join(ReceiptRow, ReceiptRow.id == ItemRow.receipt_id)
                .where(ReceiptRow.status == "approved")
                .order_by(ReceiptRow.created_at.desc(), ItemRow.id.asc())
            ).all()
            return [
                {
                    "receipt_id": receipt.id,
                    "created_at": receipt.created_at.isoformat(),
                    "discord_user_id": receipt.discord_user_id,
                    "version_number": version.version_number,
                    "name": item.name,
                    "original_name": item.original_name,
                    "category": item.category,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "currency": item.currency,
                    "confidence": item.confidence,
                }
                for receipt, version, item in rows
            ]

    def latest_parsed(self, version_id: int) -> ParsedReceipt:
        with self.session_factory() as session:
            version = self._get_version(session, version_id)
            return TypeAdapter(ParsedReceipt).validate_python(json.loads(version.parsed_json))

    @staticmethod
    def _get_receipt(session: Session, receipt_id: int) -> ReceiptRow:
        receipt = session.get(ReceiptRow, receipt_id)
        if receipt is None:
            raise ValueError(f"No receipt found for id {receipt_id}")
        return receipt

    @staticmethod
    def _get_version(session: Session, version_id: int) -> ReceiptVersionRow:
        version = session.get(ReceiptVersionRow, version_id)
        if version is None:
            raise ValueError(f"No receipt version found for id {version_id}")
        return version
