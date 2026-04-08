import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.account import Account
    from app.models.asset import Asset


class Position(UUIDMixin, Base):
    """
    Derived state for MARKET assets – current quantity and cost basis.
    Rebuilt by the engine from transaction history; not user-editable directly.
    """
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "account_id", "asset_id", name="uq_position"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    avg_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    cost_basis_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    asset: Mapped["Asset"] = relationship("Asset", back_populates="position")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="positions")

    def __repr__(self) -> str:
        return (
            f"<Position asset={self.asset_id} qty={self.quantity} "
            f"avg_cost={self.avg_cost}>"
        )
