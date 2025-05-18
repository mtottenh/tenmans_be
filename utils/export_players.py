#!/usr/bin/env python3
"""
Utility script to export all players to a CSV file with team information.

Usage:
    python export_players.py [--output players.csv]

This script exports player data including:
- Player ID
- Steam ID
- Player Name
- Status (active/banned/etc.)
- Current team in active season (if any)
- Current ELO
- Highest ELO

Dependencies:
    - asyncio
    - asyncpg
    - dotenv
"""

import asyncio
import argparse
import csv
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# Import from project modules
from sqlmodel.ext.asyncio.session import AsyncSession
from db.main import init_db, async_session
from auth.models import Player
from auth.schemas import PlayerStatus
from teams.models import Team, Roster, TeamCaptain
from teams.base_schemas import RosterStatus, TeamStatus
from competitions.models.tournaments import Tournament
from competitions.models.seasons import Season, SeasonState


async def get_active_season(session: AsyncSession) -> Optional[Season]:
    """Get the current active season"""
    from sqlmodel import select
    
    stmt = select(Season).where(Season.state == SeasonState.IN_PROGRESS)
    result = await session.execute(stmt)
    return result.scalars().first()


async def export_players_to_csv(output_file: str):
    """Export all players to a CSV file with team information."""
    from sqlmodel import select, or_
    from sqlalchemy.orm import selectinload
    
    print(f"Connecting to database...")
    await init_db()
    
    async with async_session() as session:
        # Get active season
        active_season = await get_active_season(session)
        if not active_season:
            print("WARNING: No active season found. Team information will be unavailable.")
            active_season_id = None
        else:
            print(f"Active season: {active_season.name}")
            active_season_id = active_season.id
        
        # Query players with roster info
        print("Fetching players data...")
        stmt = select(Player).options(
            selectinload(Player.team_rosters).selectinload(Roster.team).selectinload(Team.captains)
        ).order_by(Player.name)
        
        result = await session.execute(stmt)
        players = result.scalars().all()
        
        print(f"Found {len(players)} players")
        
        # Write to CSV
        print(f"Writing data to {output_file}...")
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Player ID', 
                'Steam ID', 
                'Name', 
                'Status',
                'Current Team', 
                'Is Captain',
                'Current ELO', 
                'Highest ELO',
                'Created At'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for player in players:
                # Skip system user
                if player.name == "SYSTEM":
                    continue
                
                # Find current team (if any)
                team_name = "No Team"
                is_captain = False
                
                if active_season_id:
                    # Look for active roster in current season
                    current_roster = next(
                        (r for r in player.team_rosters 
                         if r.season_id == active_season_id 
                         and r.status == RosterStatus.ACTIVE
                         and r.team.status == TeamStatus.ACTIVE),
                        None
                    )
                    
                    if current_roster:
                        team_name = current_roster.team.name
                        
                        # Check if player is captain
                        for captain in current_roster.team.captains:
                            if captain.player_id == player.id:
                                is_captain = True
                                break
                
                writer.writerow({
                    'Player ID': str(player.id),
                    'Steam ID': player.steam_id,
                    'Name': player.name,
                    'Status': player.status,
                    'Current Team': team_name,
                    'Is Captain': 'Yes' if is_captain else 'No',
                    'Current ELO': player.current_elo or 'N/A',
                    'Highest ELO': player.highest_elo or 'N/A',
                    'Created At': player.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })
    
    print(f"Export complete! Data saved to {output_file}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Export players to CSV file')
    parser.add_argument('--output', default='players.csv', help='Output CSV file (default: players.csv)')
    args = parser.parse_args()
    
    # Run the export
    asyncio.run(export_players_to_csv(args.output))