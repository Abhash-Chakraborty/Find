"""Partner sharing — one user grants another read access to their library.

Additive by design: a partner grant is a directed edge (sharer → partner). It
does NOT widen the global ``scope_media_query`` (that path guards every list
surface and is where IDOR bugs are costly); instead the dedicated ``/partners``
router exposes explicit partner-scoped *read* endpoints. A partner can browse
the sharer's browsable media but cannot mutate it.

One-directional: Alice sharing with Bob lets Bob see Alice's media; Bob's
library stays private unless he shares back. Unique on (sharer, partner).
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from find_api.core.database import Base


class PartnerShare(Base):
    """A directed read-access grant from one user to another."""

    __tablename__ = "partner_shares"

    id = Column(Integer, primary_key=True, index=True)
    # The user granting access (owner of the shared media).
    sharer_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user receiving access.
    partner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "sharer_user_id", "partner_user_id", name="uq_partner_share_pair"
        ),
    )

    def __repr__(self):
        return (
            f"<PartnerShare(sharer={self.sharer_user_id}, "
            f"partner={self.partner_user_id})>"
        )
