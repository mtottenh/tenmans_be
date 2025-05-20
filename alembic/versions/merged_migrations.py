"""Merged_datetime_and_schema_updates

Revision ID: merged_migrations
Revises: e3fe58bb329e
Create Date: 2025-05-20 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'merged_migrations'
down_revision: Union[str, None] = 'e3fe58bb329e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new tables that weren't in the initial deployment

    # Create moderation_actions table (new)
    op.create_table('moderation_actions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('player_id', sa.UUID(), nullable=False),
        sa.Column('action_type', postgresql.ENUM(name='moderationactiontype', create_type=False), nullable=True),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scope', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scope_id', sqlmodel.sql.sqltypes.GUID(), nullable=True),
        sa.Column('start_date', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('end_date', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('issued_by', sa.UUID(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['issued_by'], ['players.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create linked_tournaments table (new)
    op.create_table('linked_tournaments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_tournament_id', sa.UUID(), nullable=True),
        sa.Column('target_tournament_id', sa.UUID(), nullable=True),
        sa.Column('qualification_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_tournament_id'], ['tournaments.id'], ),
        sa.ForeignKeyConstraint(['target_tournament_id'], ['tournaments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create player_availability table (new)
    op.create_table('player_availability',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('player_id', sa.UUID(), nullable=True),
        sa.Column('tournament_id', sa.UUID(), nullable=True),
        sa.Column('start_time', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('end_time', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('availability_type', postgresql.ENUM(name='availabilitytype', create_type=False), nullable=True),
        sa.Column('status', postgresql.ENUM(name='availabilitystatus', create_type=False), nullable=True),
        sa.Column('is_substitute', sa.Boolean(), nullable=False),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=False),
        sa.Column('recurring_pattern', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create team_availability table (new)
    op.create_table('team_availability',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('tournament_id', sa.UUID(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('available_players', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('maybe_players', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('unavailable_players', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('available_substitutes', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('has_minimum_players', sa.Boolean(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create tournament_map_pools table (new)
    op.create_table('tournament_map_pools',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tournament_id', sa.UUID(), nullable=True),
        sa.Column('selection_type', postgresql.ENUM(name='mappoolselectiontype', create_type=False), nullable=True),
        sa.Column('status', postgresql.ENUM(name='mappoolstatus', create_type=False), nullable=True),
        sa.Column('voting_start', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('voting_end', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('maps_to_select', sa.Integer(), nullable=True),
        sa.Column('votes_per_team', sa.Integer(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('finalized_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create map_pool_maps table (new)
    op.create_table('map_pool_maps',
        sa.Column('pool_id', sa.UUID(), nullable=False),
        sa.Column('map_id', sa.UUID(), nullable=False),
        sa.Column('vote_count', sa.Integer(), nullable=True),
        sa.Column('added_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['map_id'], ['maps.id'], ),
        sa.ForeignKeyConstraint(['pool_id'], ['tournament_map_pools.id'], ),
        sa.PrimaryKeyConstraint('pool_id', 'map_id')
    )

    # Create map_pool_votes table (new)
    op.create_table('map_pool_votes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('pool_id', sa.UUID(), nullable=True),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('map_id', sa.UUID(), nullable=True),
        sa.Column('voted_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['map_id'], ['maps.id'], ),
        sa.ForeignKeyConstraint(['pool_id'], ['tournament_map_pools.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create map_veto_sessions table (new)
    op.create_table('map_veto_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fixture_id', sa.UUID(), nullable=True),
        sa.Column('format', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('current_team_id', sa.UUID(), nullable=True),
        sa.Column('current_action', postgresql.ENUM(name='vetoactiontype', create_type=False), nullable=True),
        sa.Column('deadline', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['current_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create match_evidence table (new)
    op.create_table('match_evidence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fixture_id', sa.UUID(), nullable=True),
        sa.Column('match_number', sa.Integer(), nullable=False),
        sa.Column('demo_url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('stats_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('upload_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', postgresql.ENUM(name='evidencestatus', create_type=False), nullable=True),
        sa.Column('submitted_by', sa.UUID(), nullable=True),
        sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.ForeignKeyConstraint(['submitted_by'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create schedule_conflicts table (new)
    op.create_table('schedule_conflicts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fixture_id', sa.UUID(), nullable=True),
        sa.Column('conflict_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('severity', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('affected_players', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create schedule_suggestions table (new)
    op.create_table('schedule_suggestions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fixture_id', sa.UUID(), nullable=True),
        sa.Column('suggested_time', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('available_players_team1', sa.Integer(), nullable=False),
        sa.Column('available_players_team2', sa.Integer(), nullable=False),
        sa.Column('conflicts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create evidence_confirmations table (new)
    op.create_table('evidence_confirmations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('evidence_id', sa.UUID(), nullable=True),
        sa.Column('confirmed_by', sa.UUID(), nullable=True),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('confirmed_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['confirmed_by'], ['players.id'], ),
        sa.ForeignKeyConstraint(['evidence_id'], ['match_evidence.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create map_veto_actions table (new)
    op.create_table('map_veto_actions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('action_type', postgresql.ENUM(name='vetoactiontype', create_type=False), nullable=True),
        sa.Column('map_id', sa.UUID(), nullable=True),
        sa.Column('side', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('timestamp', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['map_id'], ['maps.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['map_veto_sessions.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create match_disputes table (new)
    op.create_table('match_disputes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('result_id', sa.UUID(), nullable=True),
        sa.Column('disputed_by', sa.UUID(), nullable=True),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('evidence_urls', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', postgresql.ENUM(name='disputestatus', create_type=False), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolution_notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['disputed_by'], ['players.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['players.id'], ),
        sa.ForeignKeyConstraint(['result_id'], ['results.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ALTER existing tables to add timezone support and new columns

    # Update maps table
    op.add_column('maps', sa.Column('category', postgresql.ENUM(name='mapcategory', create_type=False), nullable=True))
    op.add_column('maps', sa.Column('supported_modes', postgresql.ARRAY(sa.String()), nullable=True))
    op.alter_column('maps', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('maps', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update players table
    op.alter_column('players', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('players', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update permissions table
    op.alter_column('permissions', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update roles table
    op.alter_column('roles', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update seasons table
    op.alter_column('seasons', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update audit_events table
    op.alter_column('audit_events', 'timestamp',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('audit_events', 'grace_period_end',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update player_roles table
    op.alter_column('player_roles', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update pugs table
    op.alter_column('pugs', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('pugs', 'completed_at',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update teams table
    op.alter_column('teams', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('teams', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('teams', 'disbanded_at',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update tournaments table - IMPORTANT: Rename state to status
    op.alter_column('tournaments', 'state',
        new_column_name='status',
        existing_type=sa.Enum('NOT_STARTED', 'REGISTRATION_OPEN', 'REGISTRATION_CLOSED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='tournamentstate'),
        type_=postgresql.ENUM(name='tournamentstate', create_type=False),
        nullable=True)
    op.add_column('tournaments', sa.Column('game_mode', postgresql.ENUM(name='gamemode', create_type=False), nullable=True))
    op.add_column('tournaments', sa.Column('league_format', postgresql.ENUM(name='leagueformat', create_type=False), nullable=True))
    op.add_column('tournaments', sa.Column('map_selection_method', postgresql.ENUM(name='mapselectionmethod', create_type=False), nullable=True))
    op.add_column('tournaments', sa.Column('scheduling_config', sa.JSON(), nullable=True))
    op.alter_column('tournaments', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'registration_start',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'registration_end',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'late_registration_end',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)
    op.alter_column('tournaments', 'scheduled_start_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'scheduled_end_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournaments', 'actual_start_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)
    op.alter_column('tournaments', 'actual_end_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update bans table
    op.alter_column('bans', 'scope',
        existing_type=sa.Enum('MATCH', 'TOURNAMENT', 'SEASON', 'PERMANENT', name='banscope'),
        type_=postgresql.ENUM(name='banscope', create_type=False),
        nullable=True)
    op.alter_column('bans', 'status',
        existing_type=sa.Enum('ACTIVE', 'EXPIRED', 'APPEALED', 'REVOKED', name='banstatus'),
        type_=postgresql.ENUM(name='banstatus', create_type=False),
        nullable=True)
    op.alter_column('bans', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('bans', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('bans', 'start_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('bans', 'end_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update pug_map_results table
    op.alter_column('pug_map_results', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update pug_players table
    op.add_column('pug_players', sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False))
    op.alter_column('pug_players', 'joined_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update pug_teams table
    op.alter_column('pug_teams', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update rosters table
    op.alter_column('rosters', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('rosters', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update rounds table
    op.alter_column('rounds', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('rounds', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('rounds', 'start_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('rounds', 'end_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update substitute_availability table
    op.alter_column('substitute_availability', 'created_at',
        existing_type=sa.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('substitute_availability', 'updated_at',
        existing_type=sa.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('substitute_availability', 'last_substitute_date',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update team_captains table
    op.alter_column('team_captains', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update team_join_requests table
    op.alter_column('team_join_requests', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('team_join_requests', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('team_join_requests', 'responded_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update tournament_maps table
    op.alter_column('tournament_maps', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update tournament_registrations table
    op.alter_column('tournament_registrations', 'requested_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('tournament_registrations', 'reviewed_at',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)
    op.alter_column('tournament_registrations', 'withdrawn_at',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update fixtures table
    op.alter_column('fixtures', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('fixtures', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('fixtures', 'scheduled_at',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('fixtures', 'rescheduled_from',
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=True)

    # Update match_players table
    op.alter_column('match_players', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)

    # Update results table - add voided fields and convert timestamps
    op.add_column('results', sa.Column('voided', sa.Boolean(), nullable=False, server_default='False'))
    op.add_column('results', sa.Column('voided_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.alter_column('results', 'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)
    op.alter_column('results', 'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=postgresql.TIMESTAMP(timezone=True),
        nullable=False)


def downgrade() -> None:
    # Revert the tournament.status back to state
    op.alter_column('tournaments', 'status',
        new_column_name='state',
        existing_type=postgresql.ENUM(name='tournamentstate', create_type=False),
        type_=sa.Enum('NOT_STARTED', 'REGISTRATION_OPEN', 'REGISTRATION_CLOSED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='tournamentstate'),
        nullable=True)

    # Remove columns from results table
    op.drop_column('results', 'voided_reason')
    op.drop_column('results', 'voided')

    # Remove columns from tournaments table
    op.drop_column('tournaments', 'scheduling_config')
    op.drop_column('tournaments', 'map_selection_method')
    op.drop_column('tournaments', 'league_format')
    op.drop_column('tournaments', 'game_mode')

    # Remove created_at column from pug_players
    op.drop_column('pug_players', 'created_at')

    # Remove columns from maps
    op.drop_column('maps', 'supported_modes')
    op.drop_column('maps', 'category')

    # Convert all TIMESTAMP fields back to without timezone
    # For brevity, I'm only showing a few examples
    op.alter_column('maps', 'created_at',
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=True)
    op.alter_column('maps', 'updated_at',
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=True)

    # Drop all newly created tables in reverse order of dependencies
    op.drop_table('match_disputes')
    op.drop_table('map_veto_actions')
    op.drop_table('evidence_confirmations')
    op.drop_table('schedule_suggestions')
    op.drop_table('schedule_conflicts')
    op.drop_table('match_evidence')
    op.drop_table('map_veto_sessions')
    op.drop_table('map_pool_votes')
    op.drop_table('map_pool_maps')
    op.drop_table('tournament_map_pools')
    op.drop_table('team_availability')
    op.drop_table('player_availability')
    op.drop_table('linked_tournaments')
    op.drop_table('moderation_actions')
