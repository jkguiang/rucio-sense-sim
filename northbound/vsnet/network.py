class Promise:
    def __init__(self, route, bandwidth):
        self.route = route
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

    def provision(self):
        for link in self.route:
            link.reserve(self.bandwidth)

    def free(self):
        for link in self.route:
            link.free(self.bandwidth)

    def start(self, t=None):
        self.start_time = t if t else now()
        self.provision()

    def end(self, t=None):
        self.end_time = t if t else now()
        self.free()

class BestEffort(Promise):
    def __init__(self, route):
        super().__init__(route, None)
        self.__bytes = 0.

    @property
    def bytes(self):
        return self.__bytes + self.duration*self.bandwidth

    def update(self, bandwidth):
        self.__bytes += self.duration*self.bandwidth
        self.start_time = now()
        self.bandwidth = bandwidth

    def provision(self):
        for link in self.route:
            link.register_best_effort(self)

    def free(self):
        for link in self.route:
            link.deregister_best_effort(self)

class Link:
    def __init__(self):
        # TODO: implement this
        pass

class Node:
    def __init__(self):
        # TODO: implement this
        pass

class Network:
    def __init__(self):
        # TODO: implement this
        pass
