import json
import base64
from math import radians, cos, sin, asin, sqrt

from utils.vtime import now

INFINITY = 1e12

def distance(lat1, lat2, lon1, lon2):
     # Converts degrees to radians
     lon1 = radians(lon1)
     lon2 = radians(lon2)
     lat1 = radians(lat1)
     lat2 = radians(lat2)
     # Uses Haversine formula then multiplies by 6371 KM (radius of Earth); for miles use 3956
     km_distance = 2*asin(sqrt(
         sin((lat2 - lat1)/2)**2
         + cos(lat1)*cos(lat2)*sin((lon2 - lon1)/2)**2
     ))*6371
     return round(km_distance, 3)

class Promise:
    def __init__(self, network, route, bandwidth):
        self.network = network
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
        self.start_time = t or now()
        self.network.fulfill_promise(self)

    def end(self, t=None):
        self.end_time = t or now()
        self.network.release_promise(self)
    def asdict(self):
        return {"route":self.route.asdict(),
        "bandwidth":self.bandwidth,
        "start_time":self.start_time,
        "end_time":self.end_time}

class BestEffort(Promise):
    def __init__(self, network, route):
        super().__init__(network, route, 0.)
        self.__bytes = 0.

    def __str__(self):
        return f"BestEffort({self.route})"

    @property
    def bytes(self):
        return self.__bytes + self.duration*self.bandwidth

    def update(self, bandwidth):
        self.__bytes += self.duration*self.bandwidth
        self.start_time = now()
        self.bandwidth = bandwidth

    def start(self, t=None):
        self.start_time = t or now()
        self.network.distrib_besteff(self)

    def end(self, t=None):
        self.end_time = t or now()
        self.network.release_besteff(self)

class Route:
    def __init__(self, start_node=None, end_node=None, links=None):
        self.links = links or []
        self.start_node = start_node
        self.end_node = end_node

    @property
    def link_names(self):
        return [link.name for link in self.links]

    @property
    def id(self):
        link_names = sorted(self.link_names)
        return base64.b64encode("&".join(link_names).encode("utf-8")).decode("utf-8")

    def __len__(self):
        return len(self.links)

    def __str__(self):
        return " --> ".join(self.link_names)

    def __eq__(self, other_route):
        return self.id == other_route.id

    def get_capacity(self, is_besteff=False):
        if len(self.links) > 0:
            if is_besteff:
                return min([link.beff_bandwidth/link.n_besteffs for link in self.links])
            else:
                return min([link.prio_bandwidth for link in self.links])
        else:
            return 0
    def asdict(self):
        return {"links":self.link_names,
        "start_node":self.start_node.__str__(),
        "end_node":self.end_node.__str__()}

class Link:
    def __init__(self, name, node_1, node_2, bandwidth, beff_frac, igp_metric):
        self.name = name
        self.nodes = (node_1, node_2)
        self.total_bandwidth = bandwidth
        self.beff_frac = beff_frac
        self.prio_bandwidth = bandwidth*(1 - self.beff_frac)
        self.beff_bandwidth = bandwidth*(self.beff_frac)
        self.igp_metric = igp_metric
        self.n_besteffs = 0
        self.is_spur = False
        self.__length = distance(node_1.lat, node_2.lat, node_1.lon, node_2.lon)
        
    @property
    def length(self):
       if self.is_spur:
           return INFINITY
       else:
           return self.__length
           
    def __str__(self):
        return f"Link({self.nodes})"

    def reserve(self, bandwidth, is_besteff=False):
        orig_bandwidth = self.beff_bandwidth if is_besteff else self.prio_bandwidth
        if orig_bandwidth - bandwidth < 0:
            raise ValueError(
                f"taking {bandwidth} exceeds free bandwidth ({orig_bandwidth})"
            )
        else:
            if is_besteff:
                self.beff_bandwidth -= bandwidth
            else:
                self.prio_bandwidth -= bandwidth

    def free(self, bandwidth, is_besteff=False):
        if self.beff_bandwidth + self.prio_bandwidth + bandwidth > self.total_bandwidth:
            raise ValueError(
                f"freeing {bandwidth} exceeds max bandwidth ({self.total_bandwidth})"
            )
        else:
            if is_besteff:
                self.beff_bandwidth += bandwidth
            else:
                self.prio_bandwidth += bandwidth
    def asdict(self):
        return {"name":self.name, "nodes":[self.nodes[0].name, self.nodes[1].name],
        "total_bandwidth":self.total_bandwidth,
        "beff_frac":self.beff_frac,
        "prio_bandwidth":self.prio_bandwidth,
        "beff_bandwidth":self.beff_bandwidth,
        "igp_metric":self.igp_metric,
        "n_besteffs":self.n_besteffs,
        "is_spur":self.is_spur,
        "length":self.length}

class Node:
    def __init__(self, name, lat, lon):
        self.name = name
        self.neighbors = []
        self.lat = lat
        self.lon = lon
        
    def __str__(self):
        return f"Node({self.name})"
    
    def asdict(self):
        return json.loads(json.dumps(self, default=lambda o: o.__str__()))

class Network:
    def __init__(self, network_json, coordinates_json, max_beff_passes=100, beff_frac=0.25):
        self.__nodes = {}
        self.__links = {}
        self.besteffs = []
        self.max_beff_passes = max_beff_passes
        with open(network_json, "r") as f:
            adjacencies = json.load(f).get("adjacencies")
        with open(coordinates_json, "r") as m:
            coordinates = json.load(m)
        for adjacency in adjacencies:
            # Initialize or look up start node
            start_name = adjacency.get("a")
            start_lat, start_lon = coordinates[start_name]
            if not self.has_node(start_name):
                start_node = Node(start_name, start_lat, start_lon)
                self.add_node(start_node)
            else:
                start_node = self.get_node(start_name)
            # Initialize or look up end node
            end_name = adjacency.get("z")
            end_lat, end_lon = coordinates[end_name]
            if not self.has_node(end_name):
                end_node = Node(end_name, end_lat, end_lon)
                self.add_node(end_node)
            else:
                end_node = self.get_node(end_name)
            # Resolve neighbors
            if end_node not in start_node.neighbors:
                start_node.neighbors.append(end_node)
            if start_node not in end_node.neighbors:
                end_node.neighbors.append(start_node)
            # Initialize link
            new_link = Link(
                adjacency.get("id"), 
                start_node, 
                end_node, 
                adjacency.get("mbps"), 
                beff_frac,
                adjacency.get("igpMetric")
            )
            self.add_link(new_link)

    def add_link(self, link):
        self.__links[link.name] = link

    def get_link(self, link_name):
        return self.__links[link_name]

    def find_links(self, node_1, node_2, best_only=False):
        links = []
        for link in self.links():
            if set([node_1, node_2]) == set(link.nodes):
                links.append(link)

        if len(links) == 0:
            raise KeyError(f"no link connecting {node_1.name} and {node_2.name}")

        links.sort(key=lambda link: link.prio_bandwidth, reverse=True)
        if best_only:
            return links[0]
        else:
            return links

    def links(self, names=False):
        if names:
            return self.__links.items()
        else:
            return self.__links.values()

    def has_node(self, node):
        if type(node) == Node:
            return node.name in self.__nodes
        elif type(node) == str:
            return node in self.__nodes
        else:
            return False

    def add_node(self, node):
        self.__nodes[node.name] = node

    def get_node(self, node_name):
        if not self.has_node(node_name):
            raise KeyError(f"{node_name} not in network")
        else:
            return self.__nodes[node_name]

    def nodes(self, names=False):
        if names:
            return self.__nodes.items()
        else:
            return self.__nodes.values()

    def node_names(self):
        return self.__nodes.keys()

    def get_promise(self, route_id, bandwidth=0.):
        route = self.get_route_from_id(route_id)
        if bandwidth > 0:
            return Promise(self, route, bandwidth)
        else:
            return BestEffort(self, route)

    def distrib_besteff(self, besteff=None):
        if besteff:
            self.besteffs.append(besteff)
        
        # Reset all active links
        for besteff in self.besteffs:
            for link in besteff.route.links:
                link.n_besteffs = 0
                link.beff_bandwidth = link.total_bandwidth*link.beff_frac
        
        # Register each besteff at all of its links
        for besteff in self.besteffs:
            for link in besteff.route.links:
                link.n_besteffs += 1

        # Attempt to maximize all besteff bandwidths
        total_besteff_shares = [0. for besteff in self.besteffs]
        besteff_queue = list(self.besteffs)
        n_passes = 0
        while len(besteff_queue) > 0 and n_passes <= self.max_beff_passes:
            # Resolve any besteff that has received maximal capacity
            finished_besteffs = []
            for beff_i, besteff in enumerate(besteff_queue):
                if besteff.route.get_capacity(is_besteff=True) == 0:
                    finished_besteffs.append(besteff)
                    # Update bandwidth for this besteff
                    besteff.update(total_besteff_shares[beff_i])
                    # Deregister this besteff at each link in its route
                    for link in besteff.route.links:
                        link.n_besteffs -= 1

            # Remove finished besteffs from queue
            for besteff in finished_besteffs:
                beff_i = besteff_queue.index(besteff)
                besteff_queue.pop(beff_i)
                total_besteff_shares.pop(beff_i)

            # Find then remaining bandwidth along this besteff's route
            new_besteff_shares = [0. for besteff in besteff_queue]
            for beff_i, besteff in enumerate(besteff_queue):
                beff_share = besteff.route.get_capacity(is_besteff=True)
                new_besteff_shares[beff_i] = beff_share

            # Reserve this besteff's share of the remainder
            for beff_i, besteff in enumerate(besteff_queue):
                new_beff_share = new_besteff_shares[beff_i]
                total_besteff_shares[beff_i] += new_beff_share
                for link in besteff.route.links:
                    link.reserve(new_beff_share, is_besteff=True)

            n_passes += 1

    def release_besteff(self, besteff):
        self.besteffs.remove(besteff)
        self.distrib_besteff()

    def fulfill_promise(self, promise):
        for link in promise.route.links:
            link.reserve(promise.bandwidth)

    def release_promise(self, promise):
        for link in promise.route.links:
            link.free(promise.bandwidth)

    def get_route_from_id(self, route_id):
        link_names = base64.b64decode(route_id.encode("utf-8")).decode("utf-8").split("&")
        return Route(links=[self.get_link(name) for name in link_names])

    def __reconstruct_route(self, end_node_name, prev):
        """
        Returns the route found by one of the route-finding algorithms implemented in 
        this class.
        """
        route = Route()
        route.end_node = self.get_node(end_node_name)
        this_node = route.end_node
        prev_node = prev[this_node.name]
        while prev_node != None:
            route.start_node = prev_node
            route.links.insert(0, self.find_links(prev_node, this_node, best_only=True))
            this_node = prev_node
            prev_node = prev[this_node.name]

        return route

    def __A_star_h(self, node, end_node):
        """
        Returns the estimated cost of going from the current node to the end node
        """
        return distance(node.lat, end_node.lat, node.lon, end_node.lon)

    def __A_star_g(self, node, prev_node):
        """
        Returns the actual cost of going from the previous node to the current node
        """
        link = self.find_links(prev_node, node, best_only=True)
        return link.length

    def A_star(self, start_node_name, end_node_name):
        """
        A* algorithm for finding the shortest path between two nodes in the network. 
        Minimizes the function f(node) defined as:

            f(n) = g(n) + h(n)

        where g(n) gives the actual cost of the currently known shortest path from the 
        start node to the node n and h(n) gives the estimated cost of going from the 
        node n to the end node.
        """
        start_node = self.get_node(start_node_name)
        end_node = self.get_node(end_node_name)

        queue = [start_node]

        # prev[n] = is the node immediately preceding n on the cheapest path from start 
        #           currently known
        prev = {start_node_name: None}

        # g_scores[n] = actual cost of the cheapest path from start to n 
        g_scores = {start_node_name: 0}

        # f_scores[n] = approximately how cheap a path could be from start to finish if 
        #               it goes through n 
        f_scores = {start_node_name: self.__A_star_h(start_node, end_node)}

        while len(queue) != 0:
            # Select the 'closest' node (i.e. node with minimal f score)
            queue.sort(key=lambda node: f_scores[node.name])
            this_node = queue.pop(0)
            if this_node.name == end_node.name:
                # Success
                return self.__reconstruct_route(end_node_name, prev)
            else:
                # Check neighbors
                for next_node in this_node.neighbors:
                    g_score = (
                        g_scores[this_node.name] 
                        + self.__A_star_g(next_node, this_node)
                    )
                    if next_node.name not in g_scores or g_score < g_scores[next_node.name]:
                        # This path is better than any previous one
                        prev[next_node.name] = this_node
                        g_scores[next_node.name] = g_score
                        f_scores[next_node.name] = (
                            g_score 
                            + self.__A_star_h(next_node, end_node)
                        )
                        if next_node not in queue:
                            queue.append(next_node)

    def dijkstra(self, start_node_name, end_node_name):
        """
        Dijkstra's algorithm for finding the shortest route between two nodes in the 
        network
        """
        start_node = self.get_node(start_node_name)
        # Initialize Dijkstra variables
        dist = {}
        prev = {}
        queue = []
        for node in self.nodes():
            if node == start_node:
                dist[node.name] = 0
            else:
                dist[node.name] = INFINITY
            prev[node.name] = None
            queue.append(node)

        while len(queue) > 0:
            # Find closest node
            min_dist = INFINITY
            min_dist_node = None
            for node in queue:
                if dist[node.name] < min_dist:
                    min_dist = dist[node.name]
                    min_dist_node = node
                    
            if min_dist_node == None:
                return None 

            # Remove closest node from queue
            this_node = min_dist_node
            queue.remove(min_dist_node)
            
            if this_node.name == end_node_name:
                return self.__reconstruct_route(end_node_name, prev)

            # Evaluate distances from closest node to its neighbors
            for next_node in [n for n in this_node.neighbors if n in queue]:
                link = self.find_links(this_node, next_node, best_only=True)
                alt = dist[this_node.name] + link.length
                if alt < dist[next_node.name] and dist[this_node.name] != INFINITY:
                    dist[next_node.name] = alt
                    prev[next_node.name] = this_node

        return route

    def find_routes(self, start_node_name, end_node_name, n_routes=1, algo="dijkstra"):
        """
        Find the N shortest routes (default: 1) between a start and end node in the 
        network using Yen's K shortest paths algorithm with any algorithm implemented 
        in Network (currently: Dijkstra, A*)
        """
        route_algo = getattr(self, algo)

        shortest_route = route_algo(start_node_name, end_node_name)
        spur_routes = []
        shortest_routes = [shortest_route]
        shortest_route_ids = [shortest_route.id]
                
        for i in range(1, len(shortest_route)):
            for j in range(len(shortest_route)):
                spur_routes.append(shortest_route.links[j:j+i])

        for spur_route in spur_routes[:n_routes]:
            for link in spur_route:
                link.is_spur = True  
            next_route = route_algo(start_node_name, end_node_name)
            if next_route.id not in shortest_route_ids:
                shortest_routes.append(next_route)
                shortest_route_ids.append(next_route.id)
            for link in spur_route:
                link.is_spur = False

        shortest_routes.sort(key=lambda route: sum([link.length for link in route.links]))

        return shortest_routes

    def asdict(self):
        return {"nodes": json.loads(json.dumps(self.__nodes, default=lambda o: o.asdict())), 
        "links": json.loads(json.dumps(self.__links, default=lambda o: o.asdict())), 
        "besteffs":json.loads(json.dumps(self.besteffs, default=lambda o: o.asdict())), 
        "max_beff_passes":self.max_beff_passes}
