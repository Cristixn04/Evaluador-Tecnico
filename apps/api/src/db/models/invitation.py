from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.interview import Interview
    from src.db.models.vacancy import Vacancy


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    interview_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    token_selector: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vacancy: Mapped[Vacancy] = relationship(back_populates="invitations")
    interview: Mapped[Interview | None] = relationship(back_populates="invitation")