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
     return round(km_distance/6371, 3)

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
    def __init__(self, links=None):
        self.links = links or []

    def __str__(self):
        return " --> ".join([link.name for link in self.links])

    @property
    def id(self):
        link_names = sorted([link.name for link in self.links])
        return base64.b64encode("&".join(link_names).encode("utf-8")).decode("utf-8")

    def get_capacity(self, is_besteff=False):
        if len(self.links) > 0:
            if is_besteff:
                return min([link.beff_bandwidth/link.n_besteffs for link in self.links])
            else:
                return min([link.prio_bandwidth for link in self.links])
        else:
            return 0

class Link:
    def __init__(self, name, node_1, node_2, bandwidth, beff_frac, igp_metric, 
                 lat, lon):
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

class Node:
    def __init__(self, name, lat, lon):
        self.name = name
        self.neighbors = {}
        self.lat = lat
        self.lon = lon
        
    def __str__(self):
        return f"Node({self.name})"

class Network:
    def __init__(self, network_json, location_data, max_beff_passes=100, beff_frac=0.25):
        self.nodes = {}
        self.links = {}
        self.besteffs = []
        self.max_beff_passes = max_beff_passes
        with open(network_json, "r") as f:
            adjacencies = json.load(f).get("adjacencies")
        for adjacency in adjacencies:
            # Initialize nodes
            start_name = adjacency.get("a")
            end_name = adjacency.get("z")
            with open(location_data, "r") as m:
                points = json.load(m)
                lat = float(points[start_name][0])
                lon = float(points[start_name][1])
            if start_name not in self.nodes:
                start_node = Node(start_name, lat, lon)
                self.nodes[start_node.name] = start_node
            else:
                start_node = self.nodes[start_name]
            if end_name not in self.nodes:
                end_node = Node(end_name, lat, lon)
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
                beff_frac,
                adjacency.get("igpMetric"),
                lat,
                lon,
            )

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
        print(f"FULFILLING {promise}")
        for link in promise.route.links:
            link.reserve(promise.bandwidth)

    def release_promise(self, promise):
        print(f"RELEASING {promise}")
        for link in promise.route.links:
            link.free(promise.bandwidth)

    def get_route_from_id(self, route_id):
        link_names = base64.b64decode(route_id.encode("utf-8")).decode("utf-8").split("&")
        return Route(links=[self.links[name] for name in link_names])

    def get_links(self, node_1, node_2):
        links = []
        for link in self.links.values():
            if set([node_1, node_2]) == set(link.nodes):
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
                break

            # Evaluate distances from closest node to its neighbors
            for next_node in [n for n in this_node.neighbors.values() if n in queue]:
                links = self.get_links(this_node, next_node)
                alt = dist[this_node.name] + links[0].length
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

    def YenKSP(self, start_node_name, end_node_name, k):  
        
        shortest_path = self.dijkstra(start_node_name, end_node_name)
        spur_paths = {}
        kshortest_paths = []
        
        test = []
        for i in shortest_path.links:  
            test.append(i.name)
                
        for i in range(1, len(test)):
            for j in range(len(test)):
                spur_path = shortest_path.links[j:j+i]
                spur_path_id = ",".join([link.name for link in spur_path])
                spur_paths[spur_path_id] = spur_path

        for spur_path in list(spur_paths.values())[:k]:
            for link in spur_path:
                link.is_spur = True  
            next_path = self.dijkstra(start_node_name, end_node_name)
            kshortest_paths.append(next_path)
            for link in spur_path:
                link.is_spur = False
        return kshortest_paths