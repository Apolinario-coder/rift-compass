import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("recommendations")
