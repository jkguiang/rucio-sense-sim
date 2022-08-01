import json
import base64

INFINITY = 1e12

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

    def start(self, t=None):
        self.start_time = t if t else now()

    def end(self, t=None):
        self.end_time = t if t else now()

class BestEffort(Promise):
    def __init__(self, route):
        super().__init__(route, None)
        self.__bytes = 0.

    @property
    def bytes(self):
        return self.__bytes + self.duration*self.bandwidth

    def update(self):
        self.__bytes += self.duration*self.bandwidth
        self.start_time = now()
        # self.bandwidth = 

    def provision(self):
        for link in self.route:
            link.register_best_effort(self)

    def free(self):
        for link in self.route:
            link.deregister_best_effort(self)

class Route:
    def __init__(self, links=None):
        self.links = links or []

    @property
    def id(self):
        link_names = sorted([link.name for link in self.links])
        return base64.b64encode("&".join(link_names).encode("utf-8")).decode("utf-8")

    def get_capacity(self):
        if len(self.links) > 0:
            return min([link.prio_bandwidth for link in self.links])
        else:
            return 0

class Link:
    def __init__(self, name, node_1, node_2, bandwidth, best_effort_frac, igp_metric):
        self.name = name
        self.nodes = (node_1, node_2)
        self.total_bandwidth = bandwidth
        self.prio_bandwidth = bandwidth*(1 - best_effort_frac)
        self.best_effort_bandwidth = bandwidth*(best_effort_frac)
        self.igp_metric = igp_metric
        self.best_effort_promises = []

    def register_best_effort(self, promise):
        self.best_effort_promises.append(promise)

    def deregister_best_effort(self, promise):
        self.best_effort_promises.remove(promise)

    def reserve(self, bandwidth):
        if self.prio_bandwidth - bandwidth < 0:
            raise ValueError(
                f"taking {bandwidth} exceeds current free bandwidth (self.prio_bandwidth)"
            )
        else:
            self.prio_bandwidth -= bandwidth

    def free(self, bandwidth):
        if self.best_effort_bandwidth + self.prio_bandwidth + bandwidth > self.total_bandwidth:
            raise ValueError(
                f"freeing {bandwidth} exceeds current max bandwidth (self.total_bandwidth)"
            )
        else:
            self.prio_bandwidth += bandwidth

class Node:
    def __init__(self, name):
        self.name = name
        self.neighbors = {}

    def __str__(self):
        return f"Node({self.name})"

class Network:
    def __init__(self, network_json, max_best_effort_passes=100):
        self.nodes = {}
        self.links = {}
        self.max_best_effort_passes = max_best_effort_passes
        with open(network_json, "r") as f:
            adjacencies = json.load(f).get("adjacencies")
        for adjacency in adjacencies:
            # Initialize nodes
            start_name = adjacency.get("a")
            end_name = adjacency.get("z")
            if start_name not in self.nodes:
                start_node = Node(start_name)
                self.nodes[start_node.name] = start_node
            else:
                start_node = self.nodes[start_name]
            if end_name not in self.nodes:
                end_node = Node(end_name)
                self.nodes[end_node.name] = end_node
            else:
                end_node = self.nodes[end_name]
            # Resolve neighbors
            if end_name not in start_node.neighbors:
                start_node.neighbors[end_name] = end_node
            if start_name not in end_node.neighbors:
                end_node.neighbors[start_name] = start_node
            # Initialize link
            link_name = adjacency.get("id")
            self.links[link_name] = Link(
                link_name, 
                start_node, 
                end_node, 
                adjacency.get("mbps"), 
                adjacency.get("igpMetric")
            )

    def fulfill_promise(promise):
        if type(promise) == BestEffort:
            for link in promise.route.links:
                link.register_best_effort(promise)
        else:
            for link in promise.route.links:
                link.reserve(self.bandwidth)

    def release_promise(promise):
        if type(promise) == BestEffort:
            for link in promise.route.links:
                link.deregister_best_effort(promise)
        else:
            for link in promise.route.links:
                link.free(self.bandwidth)

    def get_route_from_id(self, route_id):
        link_names = base64.b64decode(route_id.encode("utf-8")).decode("utf-8").split("&")
        return Route(links=[self.links[name] for name in link_names])

    def get_links(self, node_1, node_2):
        nodes = set((node_1, node_2))
        links = []
        for link in self.links.values():
            if set(nodes) == set(link.nodes):
                links.append(link)

        if len(links) == 0:
            raise KeyError(f"no link connecting {node_1.name} and {node_2.name}")

        return sorted(links, key=lambda link: link.prio_bandwidth, reverse=True)

    def dijkstra(self, start_node_name, end_node_name):
        dist = {}
        prev = {}
        queue = []
        for node in self.nodes.values():
            if node == self.nodes[start_node_name]:
                dist[node.name] = 0
            else:
                dist[node.name] = INFINITY
            prev[node.name] = None
            queue.append(node)

        while len(queue) > 0:
            # Find closest node
            min_dist = INFINITY
            min_dist_node = -1
            for node in queue:
                if dist[node.name] < min_dist:
                    min_dist = dist[node.name]
                    min_dist_node = node

            # Remove closest node from queue
            this_node = min_dist_node
            queue.remove(min_dist_node)

            if this_node.name == end_node_name:
                break

            # Evaluate distances from closest node to its neighbors
            alt = dist[this_node.name] + 1
            for next_node in [n for n in this_node.neighbors.values() if n in queue]:
                if alt < dist[next_node.name] and dist[this_node.name] != INFINITY:
                    dist[next_node.name] = alt
                    prev[next_node.name] = this_node

        # Reconstruct route
        route = Route()
        this_node = self.nodes[end_node_name]
        prev_node = prev[this_node.name]
        while prev_node != None:
            route.links.insert(0, self.get_links(prev_node, this_node)[0])
            this_node = prev_node
            prev_node = prev[this_node.name]

        return route
