from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.enums import Difficulty

if TYPE_CHECKING:
    from src.db.models.interview import Interview


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(
            Difficulty,
            name="difficulty",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        index=True,
    )
    language: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scenario_preview: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )

    interviews: Mapped[list[Interview]] = relationship(back_populates="problem")
