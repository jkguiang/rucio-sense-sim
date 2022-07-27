from utils.vtime import now
from northbound.vsnet.network import Promise, BestEffort

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
                self.promises[-1].end(t=end_time)
                self.end_time = end_time
                self.is_active = False
                self.is_finished = True

    def update(self, route, bandwidth=None):
        self.check()
        if bandwidth:
            promise = Promise(route, bandwidth)
        else:
            promise = BestEffort(route)

        if self.is_active and len(self.promises) > 0:
            start_time = now()
            promise.start(t=start_time)
            self.promises[-1].end(t=start_time)

        self.promises.append(promise)

    def start(self):
        self.promises[-1].start()
        self.start_time = self.promises[-1].start_time
        self.is_active = True
