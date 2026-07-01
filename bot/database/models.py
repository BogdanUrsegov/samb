import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text, Integer, String, Boolean, Float, DateTime, ForeignKey, Index

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)

# ─── Models ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    registration_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    messages_received: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    link_clicks: Mapped[int] = mapped_column(Integer, default=0)
    custom_start_param: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    last_activity: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    received_message_id: Mapped[int] = mapped_column(Integer)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    sender_message_id: Mapped[int] = mapped_column(Integer)
    sender_first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_messages_recipient_id", "recipient_id"),
        Index("idx_messages_sender_id", "sender_id"),
        Index("idx_messages_received_message_id", "received_message_id"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ReferralLink(Base):
    __tablename__ = "referral_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    viewer_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_referral_links_code", "code"),
    )


class ReferralClick(Base):
    __tablename__ = "referral_clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referral_id: Mapped[int] = mapped_column(ForeignKey("referral_links.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_referral_clicks_referral_id", "referral_id"),
    )
