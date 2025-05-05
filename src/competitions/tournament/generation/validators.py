# competitions/tournament/generation/validators.py
from typing import List, Dict, Any
from datetime import datetime

from competitions.models.tournaments import Tournament, TournamentType, TournamentState
from competitions.models.rounds import Round
from teams.models import Team
from competitions.base_schemas import LeagueFormat

class ValidationError(Exception):
    """Base exception for tournament validation errors"""
    pass

class TournamentValidator:
    """Validates tournament configuration and requirements"""
    
    @staticmethod
    def validate_tournament_config(tournament: Tournament):
        """Validate tournament configuration"""
        if not tournament.format_config:
            raise ValidationError("Tournament format configuration is required")
            
        if tournament.type == TournamentType.REGULAR:
            TournamentValidator._validate_regular_config(tournament)
        elif tournament.type == TournamentType.KNOCKOUT:
            TournamentValidator._validate_knockout_config(tournament)
            
    @staticmethod
    def _validate_regular_config(tournament: Tournament):
        """Validate regular (league) tournament configuration"""
        config = tournament.format_config
        required_fields = {'match_format'}
        missing = required_fields - set(config.keys())
        if missing:
            raise ValidationError(f"Missing required configuration fields: {missing}")
            
        if config['match_format'] not in {'bo1', 'bo2', 'bo3', 'bo5'}:
            raise ValidationError("Invalid match format")
            
        # Note: Removed 'teams_per_group' as most tournaments have single group
        # If needed, this can be part of the format_config for specific strategies
            
    @staticmethod
    def _validate_knockout_config(tournament: Tournament):
        """Validate knockout tournament configuration"""
        config = tournament.format_config
        required_fields = {'seeding_type', 'match_format'}
        missing = required_fields - set(config.keys())
        if missing:
            raise ValidationError(f"Missing required configuration fields: {missing}")
            
        valid_seeding = {'random', 'manual', 'elo', 'standings'}
        if config['seeding_type'] not in valid_seeding:
            raise ValidationError(f"Invalid seeding type. Must be one of: {valid_seeding}")
            
        if config['match_format'] not in {'bo1', 'bo3', 'bo5'}:
            raise ValidationError("Invalid match format")
            
    @staticmethod
    def validate_tournament_dates(tournament: Tournament):
        """Validate tournament dates"""
        now = datetime.now()
        
        if tournament.scheduled_start_date < now:
            raise ValidationError("Tournament cannot start in the past")
            
        if tournament.scheduled_end_date <= tournament.scheduled_start_date:
            raise ValidationError("End date must be after start date")
            
        if tournament.registration_end >= tournament.scheduled_start_date:
            raise ValidationError("Registration must end before tournament starts")
            
        if tournament.allow_late_registration and tournament.late_registration_end:
            if tournament.late_registration_end >= tournament.scheduled_start_date:
                raise ValidationError("Late registration must end before tournament starts")
                
    @staticmethod
    def validate_teams(teams: List[Team], tournament: Tournament):
        """Validate teams meet tournament requirements"""
        if len(teams) < tournament.min_teams:
            raise ValidationError(
                f"Not enough teams. Minimum {tournament.min_teams} required."
            )
            
        if len(teams) > tournament.max_teams:
            raise ValidationError(
                f"Too many teams. Maximum {tournament.max_teams} allowed."
            )
            
        # Validate team sizes
        for team in teams:
            active_roster_count = sum(1 for roster in team.rosters if roster.status == 'ACTIVE')
            if active_roster_count < tournament.min_team_size:
                raise ValidationError(
                    f"Team {team.name} does not meet minimum roster size "
                    f"of {tournament.min_team_size}"
                )
                
    @staticmethod
    def validate_round_dates(rounds: List[Round], tournament: Tournament):
        """Validate round dates fit within tournament schedule"""
        if not rounds:
            return
            
        # Check first round starts with tournament
        if rounds[0].start_date < tournament.scheduled_start_date:
            raise ValidationError("First round cannot start before tournament")
            
        # Check last round ends with tournament
        if rounds[-1].end_date > tournament.scheduled_end_date:
            raise ValidationError("Last round cannot end after tournament")
            
        # Check round continuity
        for i in range(len(rounds) - 1):
            if rounds[i].end_date > rounds[i + 1].start_date:
                raise ValidationError(
                    f"Round {i + 1} ends after round {i + 2} starts"
                )