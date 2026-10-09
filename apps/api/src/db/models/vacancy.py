from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.enums import Seniority

if TYPE_CHECKING:
    from src.db.models.auth import Organization
    from src.db.models.interview import Interview


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    role_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    seniority: Mapped[Seniority | None] = mapped_column(
        Enum(
            Seniority,
            name="seniority",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
        index=True,
    )
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    organization: Mapped[Organization | None] = relationship(back_populates="vacancies")
    interviews: Mapped[list[Interview]] = relationship(back_populates="vacancy")
