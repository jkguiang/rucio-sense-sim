from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from northbound.vsnet.connection import Connection
from northbound.vsnet.network import Network

vsnet = Network()
api = FastAPI()

connections = {}

def find_connection(connection_id):
    if connection_id not in connections:
        raise HTTPException(
            status_code=404,
            detail=f"connection with {connection_id} not found"
        )
    else:
        return connections[connection_id]

async def construct_history():
    return [connection.__dict__ for connection in connections.values()]

@api.get("/history")
async def get_history():
    return await construct_history()

@api.get("/connections/{connection_id}/check")
def check_connection(connection_id: str):
    """
    Check status of VSNet Connection

    - **connection_id**: identifier for connection (RuleID_Src_Dst)
    """
    connection = find_connection(connection_id)
    connection.check()
    return {
        "is_finished": connection.is_finished,
        "remaining_time": connection.compute_remaining_time()
    }

@api.post("/connections")
def create_connection(burro_id: str, src: str, dst: str, total_data: float):
    """
    Create VSNet Connection

    - **burro_id**: identifier for connection from Burro (rule ID)
    - **src**: name of source site (RSE name)
    - **dst**: name of destination site (RSE name)
    - **total_data**: total amount of data to be transfered from src to dst in bytes
    """
    connection_id = f"{burro_id}_{src}_{dst}"
    connections[connection_id] = Connection(connection_id, total_data)

@api.put("/connections/{connection_id}/update")
def update_connection(connection_id: str, bandwidth: float, route_id: str):
    """
    Update VSNet Connection with a given ID with a new bandwidth

    - **connection_id**: identifier for connection
    - **bandwidth**: bandwidth provision in bytes/sec
    """
    connection = find_connection(connection_id)
    route = vsnet.get_route(route_id)
    connection.update(route, bandwidth=bandwidth)

@api.put("/connections/{connection_id}/start")
def start_connection(connection_id: str):
    """
    Start VSNet "transfers" across a Connection with a given ID

    - **connection_id**: identifier for connection
    """
    connection = find_connection(connection_id)
    if not connection.is_active:
        connection.start()
