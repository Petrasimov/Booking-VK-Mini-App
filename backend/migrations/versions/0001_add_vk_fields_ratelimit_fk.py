"""Add VK fields, rate_limit table, FK and indexes

Revision ID: 0001
Revises:
Create Date: 2026-02-20

Применяется к существующим установкам, где таблицы уже созданы через create_all().
Каждое изменение защищено проверкой на существование — миграция идемпотентна.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(inspector: Inspector, table: str, index: str) -> bool:
    return any(i["name"] == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    # --- 1. Колонки VK в таблице reservation ---
    if "reservation" in existing_tables:
        if not _column_exists(inspector, "reservation", "vk_user_id"):
            op.add_column("reservation", sa.Column("vk_user_id", sa.Integer(), nullable=True))

        if not _column_exists(inspector, "reservation", "vk_notifications"):
            op.add_column(
                "reservation",
                sa.Column("vk_notifications", sa.Boolean(), nullable=False, server_default="false"),
            )

        if not _column_exists(inspector, "reservation", "appeared"):
            op.add_column("reservation", sa.Column("appeared", sa.Boolean(), nullable=True))

        if not _column_exists(inspector, "reservation", "check"):
            op.add_column("reservation", sa.Column("check", sa.Integer(), nullable=True))

        # Индексы на reservation
        if not _index_exists(inspector, "reservation", "ix_reservation_date"):
            op.create_index("ix_reservation_date", "reservation", ["date"])

        if not _index_exists(inspector, "reservation", "ix_reservation_phone_date"):
            op.create_index(
                "ix_reservation_phone_date", "reservation", ["phone", "date"]
            )

    # --- 2. Индекс на scheduled_task ---
    if "scheduled_task" in existing_tables:
        if not _index_exists(inspector, "scheduled_task", "ix_task_pending"):
            op.create_index(
                "ix_task_pending", "scheduled_task", ["completed", "scheduled_at"]
            )

    # --- 3. Таблица rate_limit (новая) ---
    if "rate_limit" not in existing_tables:
        op.create_table(
            "rate_limit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ip", sa.String(50), nullable=False),
            sa.Column("window_start", sa.DateTime(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index("ix_rate_limit_ip", "rate_limit", ["ip"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "rate_limit" in existing_tables:
        op.drop_table("rate_limit")

    if "reservation" in existing_tables:
        for idx in ("ix_reservation_phone_date", "ix_reservation_date"):
            if _index_exists(inspector, "reservation", idx):
                op.drop_index(idx, table_name="reservation")

        for col in ("vk_user_id", "vk_notifications", "appeared", "check"):
            if _column_exists(inspector, "reservation", col):
                op.drop_column("reservation", col)

    if "scheduled_task" in existing_tables:
        if _index_exists(inspector, "scheduled_task", "ix_task_pending"):
            op.drop_index("ix_task_pending", table_name="scheduled_task")
