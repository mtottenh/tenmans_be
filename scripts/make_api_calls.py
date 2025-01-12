
import httpx
import json
import asyncio
import logging
logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG
)


teams = { "BongoBabes" : [
    {
        'name' :  'Murphy',
        'SteamID' : "76561197971721556",
    },
    {
        'name' :  'Righthearted',
        'SteamID' : "76561198189100227",
    },
    {
        'name' :  'Nigel Mirage',
        'SteamID' : "76561198061555483",
    },
    {
        'name' :  'Spicy Nugs',
        'SteamID' : "76561198104461973",
    },
    {
        'name' :  'KriBabi',
        'SteamID' : "76561198074062893",
    },
    {
        'name' :  'Jonny',
        'SteamID' : "76561198141940079",
    },
    {
        'name' :  'Kris',
        'SteamID' : "76561198141940079",
    },

] ,
"Old Gits" : [
    {
        'name' :  'Padwan',
        'SteamID' : "76561197985524918",
    },
    {
        'name' :  'Daggerman',
        'SteamID' : "76561197969684583",
    },
    {
        'name' :  'Gnome',
        'SteamID' : "76561198019332496",
    },
    {
        'name' :  'Poke',
        'SteamID' : "76561197970990202",
    },
    {
        'name' :  'Shredder',
        'SteamID' : "76561198253275090",
    },
    {
        'name' :  'Zan',
        'SteamID' : "76561198826056418",
    },
],
"YerMum" : [], "Seven Zulu" : [], "GimpsnHoes" : [], "Ultimate Crew" : [] }
for t in teams:
    for p in teams[t]:
        p['email'] = p['name'] + "@gmail.com"
        p['password'] = 'test-password'


async def create_players(client, teams):
    tasks = []
    for t in teams:
        for p in teams[t]:
            tasks.append(client.post ("http://localhost:8000/api/v1/players/signup", data=json.dumps(p)))
    return tasks

async def login_player(client, player):
    try:
        response = await client.post("http://localhost:8000/api/v1/players/login", data=json.dumps({ 'email' : player['email'], 'password': player['password']}))
        token = response.json()
        player['uid'] = token['player']['uid']
        player['token'] = token['access_token']
        return (token['access_token'], token['player']['uid'])
    except Exception as e:
        print ( e)


async def join_team(client, team, player, token):
    try:
        print(f"Player {player['name']} joining {team}")
        response = await client.patch(f"http://localhost:8000/api/v1/teams/name/{team}/roster",
                                        headers={'Authorization' :'Bearer ' + token },
                                        data=json.dumps({ 'players' : [ {'name' : player['name']} ]})
                                        )

        print (response.json())
    except Exception as e:
        print (e)

async def join_teams(client, teams):
    tasks = []
    for name, players in teams.items():
        for player in players:
            tasks.append(join_team(client, name, player, player['token']))  # Schedule the join task
    # Run all join tasks concurrently
    await asyncio.gather(*tasks)

async def accept_join_request(client, name,player,token):
    try:
        print(f"Player {player['name']} being marked active on team {name} uid: {player['uid']}")
        response = await client.patch(f"http://localhost:8000/api/v1/teams/name/{name}/roster/active",
                                        headers={'Authorization' :'Bearer ' + token },
                                        data=json.dumps({ 'player' :  {'id' : player['uid']} })
                                        )

        print ("Response " + str(response.json()))
    except Exception as e:
        print (e)

async def confirm_members(client, teams):
    for name, players in teams.items():
        tasks = []
        for player in players:
            # Wait for the login token
            # (_, _) = await login_player(player)
            tasks.append(accept_join_request(client, name, player, players[0]['token']))  # Schedule the join task
        # Run all join tasks concurrently
        await asyncio.gather(*tasks)


async def create_all_maps(client, token):
    tasks = []
    for map in ['ancient', 'anubis', 'dust2', 'inferno', 'mirage', 'nuke', 'overpass', 'vertigo']:
        tasks.append(create_map(client, token, map))
    await asyncio.gather(*tasks)


async def create_map(client, token, map):
    try:
        print(f"Createing Map: {map}")

        files={'img' : (f"{map}.jpg", open(f"assets/maps/{map}.jpg", 'rb'))}
        response = await client.post("http://localhost:8000/api/v1/maps/",
                                        headers={'Authorization' :'Bearer ' + token
                                                 }, data={ 'name' : map}, files=files)
        print(response.text)
        print(response.json())
        if response.status_code != httpx.codes.CREATED:
            print("Map create failed")
    except Exception as e:
        print (e)
        exit(1)

async def create_team(client, token, team):
    try:
        print(f"Creating team with name {team}")

        files={'logo' : (f"{team}_logo.png", open('bongo_drum_logo_24x24.png', 'rb'))}
        response = await client.post("http://localhost:8000/api/v1/teams/",
                                        headers={'Authorization' :'Bearer ' + token
                                                 }, data={ 'name' : team}, files=files)#data=json.dumps({ 'name' : team}))
        print(response.text)
        print(response.json())
        if response.status_code != httpx.codes.CREATED:
            print("Team create failed")
    except Exception as e:
        print (e)
        exit(1)


async def create_teams(client, teams):
    tasks = []
    for name, players in teams.items():
        if len(players) != 0:
            tasks.append(create_team(client, players[0]['token'], name))  # Schedule the join task
    # Run all join tasks concurrently
    await asyncio.gather(*tasks)


async def create_and_activate_season(client, season, token):
    try:
        response = await client.post("http://localhost:8000/api/v1/seasons/",
                    headers={'Authorization' :'Bearer ' + token },
                    data=json.dumps({
                        'name' : season
                    })
                    )
        print (response.json())
        resp2 = await client.patch(f"http://localhost:8000/api/v1/seasons/active/{season}",
                                    headers={'Authorization' :'Bearer ' + token },
                                    )
        print (resp2.json())
    except Exception as e:
        print (e)

async def get_active_season(client, token):
    try:
        response = await client.get("http://localhost:8000/api/v1/seasons/active",
                                     headers={'Authorization' :'Bearer ' + token },
                                     )
        return response.json()
    except Exception as e:
        print (e)

async def generate_group_stage(client, token, season_id):
    try:
        response = await client.post(f"http://localhost:8000/api/v1/seasons/id/{season_id}/group_stage/generate",
                                     headers={'Authorization' :'Bearer ' + token },
                                     )
        print(response.json())
    except Exception as e:
        print (e)

async def create_db_content():
    print ("Hello: ")
    async with httpx.AsyncClient(timeout=60) as client:
        create_player_tasks = await create_players(client, teams)
        await asyncio.gather(*create_player_tasks)

        login_player_tasks = []
        for players in teams.values():
            for p in players:
                login_player_tasks.append(login_player(client, p))
        await asyncio.gather(*login_player_tasks)
        await create_all_maps(client, teams['BongoBabes'][0]['token'])
        await create_and_activate_season(client, 'Season 1', teams['BongoBabes'][0]['token'])
        await create_teams(client, teams)
        await join_teams(client, teams)
        await confirm_members(client, teams)
        season = await get_active_season(client, teams['BongoBabes'][0]['token'])
        await generate_group_stage(client, teams['BongoBabes'][0]['token'], season['id'])

if __name__ == "__main__":
    asyncio.run(create_db_content())
