from typing import List
from sqlmodel import Session, select, func
from datetime import timedelta, datetime
from .models import Round, Fixture
from src.teams.models import Team, Roster, Season
import uuid

async def get_teams_with_min_players(season_id: uuid.UUID, min_players: int, session: Session) -> List[Team]:
    # Query to count unique player_uids for each team in the specified season
    results = (
       await session.exec(
            select(Team)
            .join(Roster, Team.id == Roster.team_id)
            .where(Roster.season_id == season_id)
            .where(Roster.pending == False)
            .group_by(Team.id)
            .having(func.count(func.distinct(Roster.player_uid)) > min_players)
        )
    ).all()
    return results

async def create_round_robin_fixtures_with_rounds(season_id: uuid.UUID, session: Session):
    # Fetch all teams in the given season
    teams = await get_teams_with_min_players(season_id, 5, session)
    team_ids = [team.id for team in teams]
    
    if len(team_ids) % 2 != 0:
        # If the number of teams is odd, add a 'bye' team (None) for round-robin balancing
        team_ids.append(None)
    
    num_teams = len(team_ids)
    rounds = num_teams - 1  # Total rounds needed for one complete round-robin
    
    # Scheduling parameters
    current_date = datetime.now()  # Start date for scheduling matches
    days_between_rounds = 7  # Days between each round

    # Generate fixtures by round
    for round_number in range(rounds):
        # Create a new round for the season
        round_instance = Round(
            season_id=season_id,
            round_number=round_number + 1  # 1-based index for rounds
        )
        session.add(round_instance)
        await session.commit()  # Commit to assign an ID to the round
        await session.refresh(round_instance)
        # Generate fixtures for this round
        round_fixtures = []
        for i in range(num_teams // 2):
            team_1 = team_ids[i]
            team_2 = team_ids[num_teams - 1 - i]
            
            if team_1 is not None and team_2 is not None:
                # Create fixtures with round_id association
                fixture_home = Fixture(
                    team_1=team_1,
                    team_2=team_2,
                    season_id=season_id,
                    round_id=round_instance.id,
                    scheduled_at=current_date,
                )
                
                fixture_away = Fixture(
                    team_1=team_2,
                    team_2=team_1,
                    season_id=season_id,
                    round_id=round_instance.id,
                    scheduled_at=current_date + timedelta(days=days_between_rounds * rounds)
                )
                
                # Add fixtures to round's fixture list
                round_fixtures.extend([fixture_home, fixture_away])
        
        # Rotate teams for the next round
        team_ids = [team_ids[0]] + [team_ids[-1]] + team_ids[1:-1]
        
        # Increment date for next round
        current_date += timedelta(days=days_between_rounds)
        
        # Add round fixtures to the session
        session.add_all(round_fixtures)
        await session.commit()

    print(f"Generated fixtures for season {season_id}, organized by rounds.")


async def get_fixtures_for_season_and_round(season_id: uuid.UUID, round_number: int, session: Session) -> List[Fixture]:
    round_instance = session.exec(
        select(Round).where(Round.season_id == season_id, Round.round_number == round_number)
    ).first()

    if not round_instance:
        return []

    fixtures = await session.exec(
        select(Fixture).where(Fixture.round_id == round_instance.id)
    ).all()

    return fixtures