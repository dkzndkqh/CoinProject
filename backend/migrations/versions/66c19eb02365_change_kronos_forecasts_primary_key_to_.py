"""change kronos_forecasts primary key to include model_name

Revision ID: 66c19eb02365
Revises: cb50efe28109
Create Date: 2026-10-31 14:22:31.737797

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "66c19eb02365"
down_revision: str | Sequence[str] | None = "cb50efe28109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("kronos_forecasts_pkey", "kronos_forecasts", type_="primary")
    op.create_primary_key(
        "kronos_forecasts_pkey",
        "kronos_forecasts",
        ["market", "horizon", "base_time", "model_name"],
    )


def downgrade() -> None:
    """원래 3개 컬럼 키로 되돌린다.

    주의: 같은 (market, horizon, base_time)에 model_name이 다른 행이 이미 쌓였다면
    (예: 1d 입력 추가 후) 중복 때문에 실패한다. 그때는 중복 행을 먼저 정리해야 한다.
    """
    op.drop_constraint("kronos_forecasts_pkey", "kronos_forecasts", type_="primary")
    op.create_primary_key(
        "kronos_forecasts_pkey",
        "kronos_forecasts",
        ["market", "horizon", "base_time"],
    )
