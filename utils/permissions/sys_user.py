
from sqlmodel.ext.asyncio.session import AsyncSession

from auth.models import Player
async def ensure_system_user(session: AsyncSession) -> Player:
    """Get or create the system user for CLI operations"""
    from auth.models import Player, AuthType, PlayerStatus
    from services.auth import auth_service
    

    system_user = await auth_service.get_player_by_name("SYSTEM", session)
    
    if not system_user:
        system_user = Player(
            name="SYSTEM",
            steam_id="0",  # Special value for system user
            auth_type=AuthType.STEAM,
            status=PlayerStatus.ACTIVE
        )
        session.add(system_user)
        await session.commit()
    
    return system_user
