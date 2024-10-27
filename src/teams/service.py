from sqlmodel.ext.asyncio.session import AsyncSession
from .schemas import TeamCreateModel, TeamUpdateModel, SeasonCreateModel
from sqlmodel import select, desc
from .models import Team, Season, Settings, Roster
from src.players.models import Player

class TeamService:
    async def get_all_teams(self, session: AsyncSession ):
        stmnt = select(Team).order_by(desc(Team.created_at))
        result = await session.exec(stmnt)
        return result.all()
    
    async def get_team_by_name(self, name: str, session: AsyncSession):
        stmnt = select(Team).where(Team.name == name)
        result = await session.exec(stmnt)
        return result.first()
    
    async def team_exists(self, name: str, session: AsyncSession):
        team = await self.get_team_by_name(name, session)
        return team is not None
        
    async def create_team(
        self, team_data: TeamCreateModel, session: AsyncSession
    ):
        team_data_dict = team_data.model_dump()
        new_team = Team(**team_data_dict)
        session.add(new_team)
        await session.commit()

        return new_team
    
    # TODO
    async def player_is_on_roster(self, player_data: Player, session: AsyncSession) -> bool:
        return True

class SeasonService:
    async def get_all_seasons(self, session: AsyncSession):
        stmnt = select(Season).order_by(desc(Season.created_at))
        result = await session.exec(stmnt)
        return result.all()

    async def create_new_season(self, season_data: SeasonCreateModel, session: AsyncSession):
        season_data_dict = season_data.model_dump()
        new_season = Season(**season_data_dict)
        session.add(new_season)
        await session.commit()

        return new_season
    
    async def get_season_by_name(self, name: str, session: AsyncSession):
        stmnt = select(Season).where(Season.name == name)
        result = await session.exec(stmnt)
        return result.first()

    async def season_exists(self, name: str, session: AsyncSession):
        season = await self.get_season_by_name(name, session)
        return season is not None
    
    async def set_active_season(self, season: Season, session: AsyncSession):
        stmnt = select(Settings).where(Settings.name == "active_season")
        result = await session.exec(stmnt)
        new_active_season_setting=Settings(name="active_season",value=season.name)
        current_season = result.first()
        if current_season:
            new_active_season_setting  = current_season
            new_active_season_setting.value = season.name
        session.add(new_active_season_setting)
        await session.commit()
        return new_active_season_setting

    async def get_active_season(self, session: AsyncSession):
        stmnt = select(Settings).where(Settings.name == "active_season")
        result = await session.exec(stmnt)
        active_season_setting = result.first()
        if active_season_setting:
            stmnt = select(Season).where(Season.name == active_season_setting.value)
            result = await session.exec(stmnt)
            return result.first()
        return None

class RosterService:
    async def add_player_to_team_roster(self, player: Player, team: Team, season: Season, session: AsyncSession):
        new_roster = Roster(team_id=team.id, player_uid=player.uid, season_id=season.id)
        session.add(new_roster)
        await session.commit()
        return new_roster
    
    async def get_roster(self, team: Team, season: Season, session: AsyncSession):
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Season.id == season.id)
        result = await session.exec(stmnt)
        return result.all()
    
    async def player_on_team(self, player: Player, team: Team, season: Season, session: AsyncSession) -> bool:
        stmnt = select(Roster).where(Roster.team_id == team.id).where(Roster.season_id == season.id).where(Roster.player_uid == player.uid)
        result = await session.exec(stmnt)
        return result.first() is not None