from typing import List, Tuple
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import timedelta, datetime
from competitions.models.fixtures import Fixture
from competitions.models.rounds import Round
from matches.models import Result
from teams.models import Team, Roster
import uuid


async def get_teams_with_min_players(season_id: uuid.UUID, min_players: int, session: AsyncSession) -> List[Team]:
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

async def create_round_robin_fixtures_with_rounds(season_id: uuid.UUID, session: AsyncSession):
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
            round_name=f"Groups Stage {round_number + 1}"
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

    print(f"Generated Group stage fixtures for season {season_id}, organized into {round_number + 1} rounds.")


async def get_fixtures_for_season_and_round(season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
    round_instance = (await session.exec(
        select(Round).where(Round.season_id == season_id, Round.round_number == round_number)
    )).first()

    if not round_instance:
        return []

    fixtures = (await session.exec(
        select(Fixture).where(Fixture.round_id == round_instance.id)
    )).all()

    return fixtures


def determine_team_scores(results: List[Result]) -> List[tuple]:
    team_scores = {}

    for result in results:
        # Extract team IDs
        team_1 = result.fixture.team_1
        team_2 = result.fixture.team_2

        # Update scores (3 for a win, 1 for a draw)
        team_scores[team_1] = team_scores.get(team_1, 0)
        team_scores[team_2] = team_scores.get(team_2, 0)

        if result.score_team_1 > result.score_team_2:
            team_scores[team_1] += 3  # Win for team_1
        elif result.score_team_1 < result.score_team_2:
            team_scores[team_2] += 3  # Win for team_2
        else:
            team_scores[team_1] += 1  # Draw
            team_scores[team_2] += 1  # Draw

    # Create a sorted list of teams based on their scores
    sorted_teams = sorted(team_scores.items(), key=lambda item: item[1], reverse=True)
    return sorted_teams  # Returns a list of (team_id, score) tuples

def determine_winners(fixtures: List[Fixture]) -> List[uuid.UUID]:
    winners = []

    for fixture in fixtures:
        # Assume results are set in the fixture
        if fixture.result and fixture.result.score_team_1 > fixture.result.score_team_2:
            winners.append(fixture.team_1)  # Team 1 wins
        elif fixture.result and fixture.result.score_team_1 < fixture.result.score_team_2:
            winners.append(fixture.team_2)  # Team 2 wins
        else:
            # In case of a draw or undefined results, handle accordingly
            # Here we can skip or handle further based on tournament rules
            raise ValueError("Results must be defined and cannot be a draw in knockout.")

    return winners

async def generate_knockout_fixtures(winning_teams: List[uuid.UUID], season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
    fixtures = []
    number_of_teams = len(winning_teams)

    # Check for odd number of teams to assign a bye if necessary
    has_bye = False
    if number_of_teams % 2 != 0:
        # Highest seed gets a bye
        bye_team = winning_teams[0]
        has_bye = True
        winning_teams = winning_teams[1:]  # Remove the bye team

    # Create the round in the database
    round_instance = Round(
        season_id=season_id,
        round_number=round_number,
        name=f'Round {round_number}'
    )
    session.add(round_instance)
    await session.commit()  # Commit to get the round ID
    await session.refresh(round_instance)
    # Generate fixtures based on the winning teams
    for match_index in range(len(winning_teams) // 2):
        team_1 = winning_teams[match_index]                # Top-seeded team
        team_2 = winning_teams[-(match_index + 1)]        # Bottom-seeded team

        fixture = Fixture(
            team_1=team_1,
            team_2=team_2,
            season_id=season_id,
            round_id=round_instance.id,
            scheduled_at=datetime.now()  # Set fixture date/time as needed
        )
        fixtures.append(fixture)

    # If there was a bye, add a fixture for the bye team
    if has_bye:
        fixtures.append(Fixture(
            team_1=bye_team,
            team_2=None,  # Bye indicates no match
            season_id=season_id,
            round_id=round_instance.id,
            scheduled_at=datetime.now()
        ))

    return fixtures


# Given the previous round number, schedule the next knockout round
async def schedule_knockout_round(season_id: uuid.UUID, round_number: int, session: AsyncSession) -> List[Fixture]:
    # Fetch results from the previous round
    previous_round_fixtures = ( await 
        session.exec(
            select(Fixture).where(Fixture.round_id == round_number)
        )
    ).all()

    # Determine winning teams from the previous round
    winning_teams = determine_winners(previous_round_fixtures)
    if (len(winning_teams) == 1):
        return None
    # Generate fixtures for the current round
    return await generate_knockout_fixtures(winning_teams, season_id, round_number + 1, session)

async def get_last_round(season_id: uuid.UUID, session: AsyncSession):
    stmnt = select(Round.round_number).where(Round.season_id == season_id).order_by(Round.round_number.desc())
    return (await session.exec(stmnt)).first()


async def initiate_knockout_tournament(season_id: uuid.UUID, session: AsyncSession):
    # Step 1: Fetch results of all fixtures from the group stage
    results = ( await session.exec(
        select(Result).join(Fixture)
        .where(Fixture.season_id == season_id)
    )).all()

    # Step 2: Determine all teams and their scores
    team_scores = determine_team_scores(results)
    last_round = get_last_round(season_id, session)
    if last_round is None:
        raise ValueError(f"No rounds played in this season {season_id}")
    # Step 3: Generate fixtures for the knockout stage based on seeding
    knockout_fixtures = await generate_knockout_fixtures(team_scores, season_id, last_round + 1, session)

    # Step 4: Insert knockout fixtures into the database
    session.add_all(knockout_fixtures)
    await session.commit()

    print(f"Scheduled knockout fixtures for season {season_id}.")

    # Example usage:
    # initiate_knockout_tournament(season_id, session)

    # # After the first round is completed, schedule the next round as needed
    # next_round_fixtures = schedule_knockout_round(season_id, 1, session)
    # session.add_all(next_round_fixtures)
    # session.commit()