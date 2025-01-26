import json
import asyncio
import logging

import argparse
import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from config import Config
from auth.models import Player
from services.auth import auth_service
from db.main import engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
import httpx 
from bs4 import BeautifulSoup


Session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
class ScrapeException(Exception):
    pass
class ParseException(Exception):
    pass

async def get_player_rank(player_id: str):
    data={}
    data['url'] = f"https://csstats.gg/player/{player_id}"
    data['cmd'] = "request.get"
   # data['maxTimeout'] = 60000,
    # We need to spawn the Flaresolverr docker container
    # And have an SSH reverse tunnel to a 'trusted' IP
    # e.g. some desktop machine somewhere.
    #
    # ssh -R 1080 $user@$host
    # 
    data['proxy'] = { 'url' : 'socks5://localhost:1080' }

    try:
        # 'http://localhost:8191/v1'
        response = httpx.post("http://host.docker.internal:8191/v1", headers={'Content-Type' : 'application/json'}, json=data)
        data = (response.json())
        print(data)
        soup = BeautifulSoup(data['solution']['response'], "html.parser")

        # Scrape the best Premier rank (update this selector based on the actual HTML structure)
        # Example: Assuming the rank is in an element like <div class="rank">Premier Rank: Gold</div>
        rank_elements = soup.select("div.rank > .cs2rating, div.best > .cs2rating")  # Adjust selector as per the actual HTML structure

        if rank_elements:
            print(f"RANK: {rank_elements}")
            ranks = []
            for rank_element in rank_elements:
                ranks.append(rank_element.get_text(strip=True).replace(',',''))
            ranks = sorted(ranks,key=int)
            best_rank = ranks[1] if len(ranks) == 2 else ranks[0]
            return {"player_id": player_id, "current_elo": ranks[0], "highest_elo": best_rank}
        else:
            with open (f"{player_id}.response.html", "w", encoding='utf-8') as f:
                f.write(response.text)
            raise ParseException(f"Rank information not found")
    except Exception as e:
        raise ScrapeException(f"An error occurred while fetching player data {e}")

async def main(args):
    async with Session() as session:
        players = await auth_service.get_unranked_players(session)
        if args.list_unranked_players:
            for p in players:
                print(f"{p.name} - {p.steam_id} - {p.current_elo} - {p.highest_elo}")
        if args.scrape_ranks:
            for p in players:
                player_rank = None
                try:
                    player_rank = await get_player_rank(p.steam_id)
                    for elo_type in ['current_elo', 'highest_elo']:
                        if elo_type in player_rank and int(player_rank[elo_type]) != getattr(p,elo_type):
                            setattr(p,elo_type,int(player_rank[elo_type]))
                    session.add(p)
                    await session.commit()
                    await session.refresh(p)
                    print(f"{p.name} - {p.steam_id} - {p.current_elo} - {p.highest_elo}")
                except Exception as e:
                    print(f"{e}")
                    break




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                    prog='Scrape player ELOs',
                    description='Updates a current user in the DBs ELO as scraped from csstats.gg',
                    epilog='Useful for the initial Admin add')
    parser.add_argument('--list-unranked-players',action='store_true')
    parser.add_argument('--scrape-ranks',action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args))
