import time
import yaml
from threading import Lock
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

psnet = FastAPI()
lock = Lock()

connections = []

with open("config.yaml", "r") as f_in:
    config = yaml.safe_load(f_in).get("psnet", {})
    time_dilation = config.get("time_dilation", 1.0)

def now():
    return time_dilation*(time.time_ns()/10**9)

class Promise:
    def __init__(self, bandwidth):
        self.bandwidth = bandwidth
        self.start_time = now()
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

class ConnectionSchema(BaseModel):
    src: str
    dst: str
    bandwidth: float
    total_data: float
    nonsense_id: str

class Connection:
    def __init__(self, src, dst, bandwidth, total_data, nonsense_id):
        self.src = src
        self.dst = dst
        self.total_data = total_data
        self.nonsense_id = nonsense_id
        self.promises = []
        self.update(bandwidth)

    @property
    def end_time(self):
        data_remaining = self.total_data
        for promise in self.promises[:-1]:
            data_remaining -= promise.bytes
        return self.promises[-1].start_time + data_remaining/self.promises[-1].bandwidth

    @property
    def is_finished(self):
        return self.end_time <= now()

    def update(self, bandwidth):
        promise = Promise(bandwidth)
        if len(self.promises) > 0:
            self.promises[-1].end_time = promise.start_time
        self.promises.append(promise)

def find_connection(nonsense_id):
    for connection in connections:
        if connection.nonsense_id == nonsense_id:
            return connection

@psnet.get("/connections/")
async def check_connection(burro_id: str, src: str, dst: str):
    nonsense_id = f"{burro_id}_{src}_{dst}"
    connection = find_connection(nonsense_id)
    if not connection:
        raise HTTPException(
            status_code=404,
            detail=f"connection with {nonsense_id} not found"
        )
    else:
        return {"result": connection.is_finished}

@psnet.post("/connections/")
async def create_connection(connection: ConnectionSchema):
    lock.acquire()
    connections.append(Connection(**connection.dict()))
    lock.release()

@psnet.put("/connections/")
async def update_connection(nonsense_id: str, bandwidth: float):
    connection = find_connection(nonsense_id)
    connection.update(bandwidth)
