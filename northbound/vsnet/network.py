import json

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
    def __init__(self, name, status=False):
        self.name = name
        self.neighbors = {}
        self.status = status

    def __str__(self):
        return f"Node({self.name})"

    def visit(self):
        self.status = True

class Network:
    def __init__(self, filename):
        self.nodes = {}
        self.links = {}
        self.filename = filename
        with open(filename, "r") as f:
            nodes_file = json.loads(f.read())
        for adjacency in nodes_file["adjacencies"]:
            start_name = adjacency.get("a")
            end_name = adjacency.get("z")
            if start_name not in self.nodes:
                node = Node(start_name)
                self.nodes[node.name] = node
            if end_name not in self.nodes:
                node = Node(end_name)
                self.nodes[node.name] = node
        for adjacency in nodes_file["adjacencies"]:
            for node in self.nodes.values():
                if node.name == adjacency.get("a") and adjacency.get("z") not in node.neighbors:
                    node.neighbors[adjacency.get("z")] = self.nodes[adjacency.get("z")]
                if node.name == adjacency.get("z") and adjacency.get("a") not in node.neighbors:
                    node.neighbors[adjacency.get("a")] = self.nodes[adjacency.get("a")]
        for adjacency in nodes_file["adjacencies"]:
            id = adjacency.get("id")
            start_name = adjacency.get("a")
            end_name = adjacency.get("z")
            bandwidth = adjacency.get("mbps")
            igp_metric = adjacency.get("igpMetric")
            link = Link(id, self.nodes[start_name], self.nodes[end_name], bandwidth, igp_metric)
            self.links[link.id] = link