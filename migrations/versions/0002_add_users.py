"""Add users table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02
"""
from alembic import op
import sqlalchemy as sa

revision      = '0002'
down_revision = '0001'
branch_labels = None
depends_on    = None

def upgrade():
    op.create_table('users',
        sa.Column('id',                sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email_encrypted',   sa.String(500), nullable=False, unique=True),
        sa.Column('email_hash',        sa.String(200), nullable=False, unique=True),
        sa.Column('password_hash',     sa.String(200), nullable=False),
        sa.Column('role',              sa.Enum('restaurant','collector','regulator', name='userrole'), nullable=False),
        sa.Column('restaurant_id',     sa.String(20),  nullable=True),
        sa.Column('created_at',        sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_users_email_hash', 'users', ['email_hash'])

def downgrade():
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS userrole")