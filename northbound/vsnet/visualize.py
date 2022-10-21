import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap
from matplotlib.collections import LineCollection
matplotlib.rcParams["figure.figsize"] = [100, 75]
import json
import pandas as pd
import random

from northbound.vsnet.network import Network

def plot_network(network, route=None, show_names=False, tag=""):
    # Get coordinates for every node in network
    all_X = []
    all_Y = []
    all_names = []
    for node in network.nodes():
        all_X.append(node.lon)
        all_Y.append(node.lat)
        all_names.append(node.name)

    # Get coordinates of every link in network
    lon1, lat1, lon2, lat2 = [], [], [], []
    for link in network.links():
        node1, node2 = link.nodes
        lon1.append(node1.lon)
        lat1.append(node1.lat)
        lon2.append(node2.lon)
        lat2.append(node2.lat)

    # Get coordinates for every node in route
    if route:
        print(f"Route from {route.start_node.name} to {route.end_node.name}:")
        lon3, lat3, lon4, lat4 = [], [], [], []
        names3, names4 = [], []
        for link in route.links:
            node1, node2 = link.nodes
            print(f"{node1.name} -- {node2.name}")
            lon3.append(node1.lon)
            lat3.append(node1.lat)
            lon4.append(node2.lon)
            lat4.append(node2.lat)
            names3.append(node1.name.split("-")[0])
            names4.append(node2.name.split("-")[0])

    m = Basemap(
        llcrnrlon=-119, llcrnrlat=20, 
        urcrnrlon=50, urcrnrlat=49,
        lat_1=33, lat_2=45, lon_0=-95,
        projection="lcc"
    )

    # Plot continents
    m.fillcontinents(color="gainsboro")

    # Translate coordinates into basemape objects
    all_x, all_y = m(all_X, all_Y)
    a, b = m(lon1, lat1)
    c, d = m(lon2, lat2) 
    # Plot entire network topology
    pts = np.c_[a, b, c, d].reshape(len(lon1), 2, 2)
    plt.gca().add_collection(LineCollection(pts, color="grey"))
    m.plot(all_x, all_y, marker="o", markersize=20, markerfacecolor="black", linewidth=0)

    # Plot route
    if route:
        e, f = m(lon3, lat3) 
        g, h = m(lon4, lat4) 

        route_pts = np.c_[e, f, g, h].reshape(len(lon3), 2, 2)
        plt.gca().add_collection(LineCollection(route_pts, color="red", linewidths=4.5))

        all_route_X = lon3 + lon4
        all_route_Y = lat3 + lat4
        all_route_names = names3 + names4

        # Remove repeats
        route_X = []
        route_Y = []
        for name, x, y in zip(all_route_names, all_route_X, all_route_Y):
            if x not in route_X or y not in route_Y:
                route_X.append(x)
                route_Y.append(y)

        route_x, route_y = m(route_X, route_Y)
        m.plot(route_x, route_y, marker="o", markersize=20, markerfacecolor="red", linewidth=0)

    if show_names:
        for i, (x, y) in enumerate(zip(all_x, all_y)):
            plt.annotate(all_names[i], (x, y), xytext=(5, 5), textcoords="offset points")

    if route:
        output_png = f"network_{route.start_node.name}_to_{route.end_node.name}.png"
    else:
        output_png = "network.png"

    if tag:
        output_png = output_png.replace(".png", f"_{tag}.png")

    plt.savefig(output_png)
    plt.clf()

if __name__ == "__main__":
    network = Network("data/esnet_adjacencies.json", "data/esnet_coordinates.json")
    print(f"- DIJKSTRA ------")
    plot_network(network, route=network.dijkstra("cern-773-cr5", "sand-cr6"), tag="dijkstra", show_names=True)
    print(f"- A* ------------")
    for route_i, route in enumerate(network.find_routes("cern-773-cr5", "sand-cr6", n_routes=5, algo="A_star")):
        print(f"- ROUTE {route_i} -------")
        plot_network(network, route=route, tag=str(route_i + 1))
    plot_network(network, route=network.A_star("fnalfcc-cr6", "sand-cr6"))
    plot_network(network, route=network.A_star("cern-773-cr5", "fnalfcc-cr6"))
    plot_network(network)
