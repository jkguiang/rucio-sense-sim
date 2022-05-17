from fastapi import FastAPI 
from pydantic import BaseModel

psnet = FastAPI()

class Connection(BaseModel):
    def __init__(self, source, sink, bandwidth, bandwidth_change_timestamps, total_data, sense_svc_id, rule_id):
        self.source = source
        self.sink = sink
        self.bandwidth = bandwidth
        self.bandwidth_change_timestamps = bandwidth_change_timestamps
        self.total_data = total_data
        self.sense_svc_id = sense_svc_id
        self.rule_id = rule_id

    def calculate_total_time(self):
        total_time, cur_timestamp = 0, 0
        data_remaining = self.total_data
        
        for i in range(len(self.bandwidth_change_timestamps)):
            if i == len(self.bandwidth_change_timestamps) - 1:
                return self.bandwidth_change_timestamps[i] + data_remaining / self.bandwidth[i]

            data_remaining -= self.bandwidth[i] * (self.bandwidth_change_timestamps[i+1] - self.bandwidth_change_timestamps[i])

# get stuff from flask server

@psnet.get("/connections/")
async def get_connection():
    pass 

@psnet.post("/connections/")
async def create_new_connection():
    pass
