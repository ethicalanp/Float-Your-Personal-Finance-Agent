"""merge post-merge-hardening and plan-features heads

Revision ID: f67592ba9691
Revises: b0c1d2e3f4a5, c1d2e3f4a5b6
Create Date: 2026-11-28 17:27:30.768084

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'f67592ba9691'
down_revision: Union[str, Sequence[str], None] = ('b0c1d2e3f4a5', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
