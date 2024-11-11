from sqlmodel.ext.asyncio.session import AsyncSession
from .schemas import TeamCreateModel, TeamUpdateModel
from sqlmodel import select, desc, func
from .models import Team, Roster, TeamCaptain
from src.seasons.models import Season
from src.players.models import Player
from typing import List
import uuid

class TeamService:
    async def get_all_teams(self, session: AsyncSession ) -> List[Team]:
        stmnt = select(Team).order_by(desc(Team.created_at))
        result = await session.exec(stmnt)
        return result.all()
    
    async def get_team_by_name(self, name: str, session: AsyncSession) -> Team | None:
        stmnt = select(Team).where(Team.name == name)
        result = await session.exec(stmnt)
        return result.first()

    async def get_team_by_id(self, id: str, session: AsyncSession) -> Team | None:
        stmnt = select(Team).where(Team.id == id)
        result = await session.exec(stmnt)
        return result.first()

    async def team_exists(self, name: str, session: AsyncSession) -> bool:
        team = await self.get_team_by_name(name, session)
        return team is not None
        
    async def create_team(
        self, team_data: TeamCreateModel, session: AsyncSession
    ) -> Team:
        team_data_dict = team_data.model_dump()
        new_team = Team(**team_data_dict)
        session.add(new_team)
        await session.commit()
        await session.refresh(new_team)
        return new_team

    async def create_captain(
        self, team: Team, player: Player, session: AsyncSession
    ) -> TeamCaptain:
        new_captain = TeamCaptain(team_id=team.id,player_uid=player.uid)
        session.add(new_captain)
        await session.commit()
        await session.refresh(new_captain)
        return new_captain

    async def get_team_captains(self, team_name: str, session: AsyncSession):
        stmnt = select(Player).where(Team.name == team_name).where(Team.id == TeamCaptain.team_id).where(Player.uid == TeamCaptain.player_uid)
        players = await session.exec(stmnt)
        return players.all()
    
    async def player_is_team_captain(self,  player: Player, team: Team, session: AsyncSession):
        stmnt = select(Player).where(Team.name == team.name).where(Team.id == TeamCaptain.team_id).where(Player.uid == TeamCaptain.player_uid).where(Player.uid == player.uid)
        result = await session.exec(stmnt)
        return not result.first() is None


class RosterService:
    async def add_player_to_team_roster(self, player: Player, team: Team, season: Season, session: AsyncSession):
        new_roster = Roster(team_id=team.id, player_uid=player.uid, season_id=season.id, pending=True)
        session.add(new_roster)
        await session.commit()
        await session.refresh(new_roster)
        return new_roster
    
    async def get_roster(self, team_name: str, season: Season, session: AsyncSession):
        stmnt = select(Player, Roster.pending).where(Roster.team_id == Team.id).where(Team.name == team_name).where(Roster.season_id == season.id).where(Roster.player_uid == Player.uid)
        result = await session.exec(stmnt)
        return result.all()
    
    async def player_on_team(self, player: Player, team: Team, season: Season, session: AsyncSession) -> bool:
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Roster.season_id == season.id).where(Roster.player_uid == player.uid)
        result = await session.exec(stmnt)
        return result.first() is not None
    
    async def player_on_active_roster(self, player: Player, team: Team, season: Season, session: AsyncSession) -> bool:
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Roster.season_id == season.id).where(Roster.player_uid == player.uid).where(Roster.pending == False)
        result = await session.exec(stmnt)
        return result.first() is not None
    
    async def player_is_pending(self, player: Player, team: Team, season: Season, session: AsyncSession) -> bool:
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Roster.season_id == season.id).where(Roster.player_uid == player.uid).where(Roster.pending == True)
        result = await session.exec(stmnt)
        return result.first() is not None
    
    async def set_player_active(self, player: Player, team: Team, season: Season, session: AsyncSession) :
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Roster.season_id == season.id).where(Roster.player_uid == player.uid).where(Roster.pending == True)
        result = await session.exec(stmnt)
        new_roster_entry = result.first()
        if new_roster_entry:
            new_roster_entry.pending = False
            session.add(new_roster_entry)
            await session.commit()
            await session.refresh(new_roster_entry)
        return new_roster_entry
        
    async def get_teams_with_min_players(self, season_id: uuid.UUID, min_players: int, session: AsyncSession) -> List[Team]:
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
