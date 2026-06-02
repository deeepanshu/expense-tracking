from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import discord

from src.db import Database
from src.formatting import format_receipt_summary
from src.receipt_parser import ReceiptParser
from src.settings import Settings, load_settings
from src.telemetry import (
    approvals_counter,
    configure_telemetry,
    image_size_histogram,
    logger,
    parse_duration_histogram,
    parse_failure_counter,
    parse_success_counter,
    receipts_received_counter,
    record_duration,
    rejections_counter,
    tracer,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ApprovalView(discord.ui.View):
    def __init__(self, db: Database, version_id: int) -> None:
        super().__init__(timeout=24 * 60 * 60)
        self.db = db
        self.version_id = version_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        self.db.approve_version(self.version_id)
        approvals_counter.add(1)
        logger.info("Receipt approved", extra={"expense_version_id": self.version_id})
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(content="✅ Approved and saved.", view=self)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        self.db.reject_receipt(self.version_id)
        rejections_counter.add(1)
        logger.info("Receipt rejected", extra={"expense_version_id": self.version_id})
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(content="❌ Rejected. Nothing was saved.", view=self)


class ExpenseTrackerBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.settings = settings
        self.db = Database(settings.database_path)
        self.parser = ReceiptParser(
            api_key=settings.openai_api_key,
            model=settings.openai_receipt_model,
            default_currency=settings.default_currency,
        )
        settings.image_dir.mkdir(parents=True, exist_ok=True)

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Discord bot logged in", extra={"expense_bot_user": str(self.user), "expense_bot_user_id": self.user.id})

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.channel.id != self.settings.receipt_channel_id:
            return

        image_attachments = [attachment for attachment in message.attachments if is_supported_image(attachment)]
        if not image_attachments:
            return

        for attachment in image_attachments:
            await self.process_attachment(message, attachment)

    async def process_attachment(self, message: discord.Message, attachment: discord.Attachment) -> None:
        if attachment.size > self.settings.max_image_bytes:
            await message.reply(f"Image is too large ({attachment.size} bytes). Please upload a smaller one.")
            return

        processing = await message.reply("🔎 Reading receipt image...")
        attributes = {
            "discord.channel_id": str(message.channel.id),
            "attachment.content_type": attachment.content_type or "unknown",
            "openai.model": self.settings.openai_receipt_model,
        }
        receipts_received_counter.add(1, attributes)
        image_size_histogram.record(attachment.size, attributes)
        logger.info(
            "Receipt image received",
            extra={
                "expense_discord_channel_id": message.channel.id,
                "expense_discord_message_id": message.id,
                "expense_image_size_bytes": attachment.size,
                "expense_content_type": attachment.content_type,
            },
        )
        try:
            with tracer.start_as_current_span("receipt.process") as span, record_duration(parse_duration_histogram, attributes):
                span.set_attribute("discord.channel_id", str(message.channel.id))
                span.set_attribute("discord.message_id", str(message.id))
                span.set_attribute("attachment.size_bytes", attachment.size)
                span.set_attribute("openai.model", self.settings.openai_receipt_model)
                image_path = await save_attachment(attachment, self.settings.image_dir)
                receipt_id = self.db.create_receipt(
                    discord_message_id=str(message.id),
                    discord_channel_id=str(message.channel.id),
                    discord_user_id=str(message.author.id),
                    image_path=image_path,
                    image_content_type=attachment.content_type,
                )
                parsed, raw = await self.parser.parse_image(image_path)
                version_id = self.db.add_version(receipt_id=receipt_id, parsed=parsed, raw_model_output=raw)
                span.set_attribute("receipt.id", receipt_id)
                span.set_attribute("receipt.version_id", version_id)
                parse_success_counter.add(1, attributes)
                summary = format_receipt_summary(parsed, receipt_id=receipt_id, version_id=version_id)
                await processing.edit(content=summary[:1900], view=ApprovalView(self.db, version_id))
        except Exception as exc:
            parse_failure_counter.add(1, attributes)
            logger.exception("Failed to parse receipt")
            await processing.edit(content=f"Failed to parse receipt: {exc}")


def is_supported_image(attachment: discord.Attachment) -> bool:
    suffix = Path(attachment.filename).suffix.lower()
    return suffix in IMAGE_EXTENSIONS and (attachment.content_type or "").startswith("image/")


async def save_attachment(attachment: discord.Attachment, image_dir: Path) -> Path:
    suffix = Path(attachment.filename).suffix.lower() or ".jpg"
    path = image_dir / f"{uuid4().hex}{suffix}"
    await attachment.save(path)
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    configure_telemetry(settings)
    bot = ExpenseTrackerBot(settings)
    asyncio.run(bot.start(settings.discord_token))


if __name__ == "__main__":
    main()
