import asyncio
import argparse
from typing import List, Optional
import sys
import os
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from config import Config
from auth.models import Player
from services.auth import auth_service
from db.main import engine

Session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_all_players(session: AsyncSession) -> List[Player]:
    return await auth_service.get_all_players(session)

async def display_players(players: List[Player]) -> None:
    print("\nPlayer List:")
    print("-" * 80)
    print(f"{'Index':<6} {'Name':<20} {'Steam ID':<20} {'Current ELO':<15} {'Highest ELO':<15}")
    print("-" * 80)
    for i, player in enumerate(players):
        print(f"{i:<6} {player.name:<20} {player.steam_id:<20} {player.current_elo or 'None':<15} {player.highest_elo or 'None':<15}")
    print("-" * 80)

def get_player_selection(max_index: int) -> Optional[int]:
    while True:
        try:
            choice = input("\nEnter player index to edit (or q to quit): ").strip()
            if choice.lower() == 'q':
                return None
            index = int(choice)
            if 0 <= index < max_index:
                return index
            print(f"Please enter a number between 0 and {max_index-1}")
        except ValueError:
            print("Please enter a valid number")

def get_elo_input(prompt: str) -> Optional[int]:
    value = input(prompt).strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        print("Invalid input - no change will be made")
        return None

async def edit_player_elo(player: Player, session: AsyncSession) -> None:
    print(f"\nEditing ELO for {player.name}")
    print(f"Current ELO: {player.current_elo}")
    print(f"Highest ELO: {player.highest_elo}")
    
    current_elo = get_elo_input("Enter new current ELO (or press Enter to skip): ")
    highest_elo = get_elo_input("Enter new highest ELO (or press Enter to skip): ")
    
    if current_elo is not None:
        player.current_elo = current_elo
    if highest_elo is not None:
        player.highest_elo = highest_elo
        
    if current_elo is not None or highest_elo is not None:
        session.add(player)
        await session.commit()
        await session.refresh(player)
        print(f"\nUpdated {player.name}")
        print(f"Current ELO: {player.current_elo}")
        print(f"Highest ELO: {player.highest_elo}")
    else:
        print("\nNo changes made")

async def main():
    async with Session() as session:
        while True:
            players = await get_all_players(session)
            await display_players(players)
            
            index = get_player_selection(len(players))
            if index is None:
                break
                
            await edit_player_elo(players[index], session)
            
            if input("\nPress Enter to continue or 'q' to quit: ").lower() == 'q':
                break

if __name__ == "__main__":
    asyncio.run(main())
