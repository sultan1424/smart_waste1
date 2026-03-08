"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # bins
    op.create_table('bins',
        sa.Column('id',            sa.String(20),  primary_key=True),
        sa.Column('name',          sa.String(100), nullable=False),
        sa.Column('location_name', sa.String(200), nullable=False),
        sa.Column('lat',           sa.Float(),     nullable=False),
        sa.Column('lng',           sa.Float(),     nullable=False),
        sa.Column('installed_at',  sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('status',        sa.Enum('operational','near_full','full','maintenance',
                                           name='binstatus'), nullable=False, server_default='operational'),
    )

    # telemetry — partitioning candidate for production
    op.create_table('telemetry',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bin_id',      sa.String(20), sa.ForeignKey('bins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ts',          sa.DateTime(timezone=True), nullable=False),
        sa.Column('fill_pct',    sa.Float(), nullable=False),
        sa.Column('weight_kg',   sa.Float(), nullable=False),
        sa.Column('temp_c',      sa.Float(), nullable=False),
        sa.Column('battery_v',   sa.Float(), nullable=False),
        sa.Column('signal_rssi', sa.Float(), nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_telemetry_bin_ts', 'telemetry', ['bin_id', 'ts'])
    op.create_index('ix_telemetry_ts',     'telemetry', ['ts'])

    # pickups
    op.create_table('pickups',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bin_id',       sa.String(20), sa.ForeignKey('bins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end',   sa.DateTime(timezone=True), nullable=False),
        sa.Column('route_id',     sa.String(50), nullable=False),
        sa.Column('priority',     sa.Enum('low','medium','high', name='pickuppriority'),
                                  nullable=False, server_default='medium'),
        sa.Column('status',       sa.Enum('planned','completed','missed', name='pickupstatus'),
                                  nullable=False, server_default='planned'),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_pickups_scheduled_at', 'pickups', ['scheduled_at'])
    op.create_index('ix_pickups_bin_id',       'pickups', ['bin_id'])

    # forecasts
    op.create_table('forecasts',
        sa.Column('id',                     sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bin_id',                 sa.String(20), sa.ForeignKey('bins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('forecast_date',          sa.Date(),  nullable=False),
        sa.Column('predicted_fill_pct',     sa.Float(), nullable=False),
        sa.Column('predicted_weight_kg',    sa.Float(), nullable=False),
        sa.Column('recommended_pickup_date',sa.Date(),  nullable=False),
        sa.Column('model_version',          sa.String(50), server_default='mock-v0.1'),
        sa.Column('created_at',             sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_forecasts_bin_date', 'forecasts', ['bin_id', 'forecast_date'])

    # reports_cache
    op.create_table('reports_cache',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bin_id',       sa.String(20), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end',   sa.Date(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('payload_json', sa.JSON, nullable=False),
    )
    op.create_index('ix_reports_cache_bin_period', 'reports_cache',
                    ['bin_id', 'period_start', 'period_end'])


def downgrade():
    op.drop_table('reports_cache')
    op.drop_table('forecasts')
    op.drop_table('pickups')
    op.drop_table('telemetry')
    op.drop_table('bins')
    op.execute("DROP TYPE IF EXISTS binstatus")
    op.execute("DROP TYPE IF EXISTS pickuppriority")
    op.execute("DROP TYPE IF EXISTS pickupstatus")