import time
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

psnet = FastAPI()

connections = {}

with open("config.yaml", "r") as f_in:
    config = yaml.safe_load(f_in).get("psnet", {})

time_dilation = config.get("time_dilation", 1.0)

def now():
    return time_dilation*(time.time_ns()/10**9)

class Promise:
    def __init__(self, bandwidth):
        self.bandwidth = bandwidth
        self.start_time = None
        self.end_time = None

    @property
    def bytes(self):
        return self.duration*self.bandwidth

    @property
    def duration(self):
        if not self.start_time:
            return 0
        elif not self.end_time:
            return now() - self.start_time
        else:
            return self.end_time - self.start_time

    def start(self):
        self.start_time = now()

class Connection:
    def __init__(self, connection_id, total_data):
        self.total_data = total_data
        self.id = connection_id
        self.promises = []
        self.is_active = False
        self.is_finished = False
        self.start_time = None
        self.end_time = None

    @property
    def duration(self):
        if not self.start_time:
            return 0
        elif not self.end_time:
            return now() - self.start_time
        else:
            return self.end_time - self.start_time

    def compute_remaining_time(self):
        if self.is_active:
            remaining_data = self.total_data
            for promise in self.promises[:-1]:
                remaining_data -= promise.bytes
            
            return remaining_data/self.promises[-1].bandwidth
        else:
            return None
    
    def compute_end_time(self):
        if self.is_active:
            return self.promises[-1].start_time + self.compute_remaining_time()
        else:
            return None

    def check(self):
        if self.is_active:
            end_time = self.compute_end_time()
            if end_time <= now():
                self.promises[-1].end_time = end_time
                self.end_time = end_time
                self.is_active = False
                self.is_finished = True

    def update(self, bandwidth):
        self.check()
        promise = Promise(bandwidth)
        if self.is_active and len(self.promises) > 0:
            promise.start()
            self.promises[-1].end_time = promise.start_time

        self.promises.append(promise)

    def start(self):
        if len(self.promises) == 0:
            # TODO: add something to handle these (best effort)
            pass
        else:
            self.promises[-1].start()
            self.start_time = self.promises[-1].start_time

        self.is_active = True

def find_connection(connection_id):
    if connection_id not in connections:
        raise HTTPException(
            status_code=404,
            detail=f"connection with {connection_id} not found"
        )
    else:
        return connections[connection_id]

@psnet.get("/connections/{connection_id}/check")
async def check_connection(connection_id: str):
    """
    Check status of PSNet Connection

    - **connection_id**: identifier for connection (RuleID_Src_Dst)
    """
    connection = find_connection(connection_id)
    connection.check()
    return {
        "is_finished": connection.is_finished,
        "remaining_time": connection.compute_remaining_time()
    }

@psnet.post("/connections")
async def create_connection(burro_id: str, src: str, dst: str, total_data: float):
    """
    Create PSNet Connection

    - **burro_id**: identifier for connection from Burro (rule ID)
    - **src**: name of source site (RSE name)
    - **dst**: name of destination site (RSE name)
    - **total_data**: total amount of data to be transfered from src to dst in bytes
    """
    connection_id = f"{burro_id}_{src}_{dst}"
    connections[connection_id] = Connection(connection_id, total_data)

@psnet.put("/connections/{connection_id}/update")
async def update_connection(connection_id: str, bandwidth: float):
    """
    Update PSNet Connection with a given ID with new bandwidth

    - **connection_id**: identifier for connection
    - **bandwidth**: bandwidth provision in bytes/sec
    """
    connection = find_connection(connection_id)
    connection.update(bandwidth)

@psnet.put("/connections/{connection_id}/start")
async def start_connection(connection_id: str):
    """
    Start PSNet "transfers" across a Connection with a given ID

    - **connection_id**: identifier for connection
    """
    connection = find_connection(connection_id)
    if not connection.is_active:
        connection.start()
