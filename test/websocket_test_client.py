import asyncio
from typing import List
from uuid import uuid4
import httpx
import websockets
import json
from src.fixtures.MapPicker.commands import *

# Base API URL
API_BASE_URL = "localhost:8000/api/v1/fixtures"

# Pug creation payload
pug_payload = {
    "team_1": "Team A",
    "team_2": "Team B"
}

async def create_new_pug():
    """
    Make an HTTP request to create a new pug and return the ID.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(f"http://{API_BASE_URL}/new_pug", json=pug_payload)
        if response.status_code == 200:
            data = response.json()
            return data.get("id")
        else:
            raise Exception(f"Failed to create pug: {response.status_code} {response.text}")

async def connect_to_websocket(pug_id):
    """
    Connect to the WebSocket and send commands.
    """
    ws_url = f"ws://{API_BASE_URL}/pug/id/{pug_id}/ws"
    async with websockets.connect(ws_url) as websocket:
        print(f"Connected to {ws_url}")
        
        # Commands to be sent
        commands : List[BaseCmd]= [
            IdentifyClientCmd(seq_no=1, client_id=str(uuid4())),
            JoinTeamCmd(seq_no=2, name="Team A"),
            AllChatCmd(seq_no=3, message="Hello World!")
        ]
        
        # Send commands
        for command in commands:
            await websocket.send(command.model_dump_json())
            print(f"Sent command: {command}")
            
            # Wait for server response
            response = await websocket.recv()
            print(f"Received response: {response}")

async def main():
    # Step 1: Create a new pug and get its ID
    pug_id = await create_new_pug()
    print(f"Created new pug with ID: {pug_id}")

    # Step 2: Connect to the WebSocket and send commands
    await connect_to_websocket(pug_id)

# Run the client
asyncio.run(main())
