import json
import yaml
import uuid
from threading import Lock
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

nonsense = FastAPI()
lock = Lock()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth")

services = {}

config = {}
with open("config.yaml", "r") as f_in:
    config = yaml.safe_load(f_in).get("nonsense", {})

profile_uuid = config.get("profile_uuid")

class Service:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.alias = ""
        self.intent = {}
        self.status = ""

def site_info_lookup(key, root_uri="", full_uri="", name=""):
    for site_info in config.get("sites", []):
        if name and name == site_info["name"]:
            return site_info.get(key, None)
        elif root_uri and root_uri == site_info["root_uri"]:
            return site_info.get(key, None)
        elif full_uri and full_uri == site_info["full_uri"]:
            return site_info.get(key, None)

@nonsense.post("/auth")
async def authenticate(form_data: OAuth2PasswordRequestForm = Depends()):
    return {"access_token": form_data.username, "token_type": "Bearer"}

# @nonsense.route("/api/profile/<profile_uuid>", methods=["GET"])
@nonsense.get("/api/profile/{profile_uuid}")
def profile(profile_uuid: str):
    with open(f"data/profiles/{profile_uuid}.json", "r") as profile_json:
        return profile_json.read()

@nonsense.delete("/api/service/{instance_uuid}")
def delete_service(instance_uuid: str):
    return

# @nonsense.route("/api/instance", methods=["GET"])
@nonsense.get("/api/instance", response_class=PlainTextResponse)
def create_instance():
    service = Service()
    lock.acquire()
    services[service.id] = service
    lock.release()
    return service.id

# @nonsense.route("/api/instance/<instance_uuid>", methods=["POST"])
@nonsense.post("/api/instance/{instance_uuid}")
def query_instance(instance_uuid: str, new_intent: dict):
    # Initialize response
    response = {
        "service_uuid": instance_uuid,
        "intent_uuid": str(uuid.uuid4()),
        "queries": []
    }

    # Load service profile
    with open(f"data/profiles/{profile_uuid}.json", "r") as profile_json:
        profile = json.load(profile_json)
        intent = profile["intent"]["data"]

    # Parse queries and edit instance data
    for query in new_intent.get("queries", []):
        ask = query["ask"]
        answer = {"asked": ask, "results": []}
        if ask == "edit":
            for option in query["options"]:
                for keychain, value in option.items():
                    connection_i = int(keychain.split("connections[")[-1].split("]")[0])
                    connection_data = intent["connections"][connection_i]
                    if "terminals" in keychain:
                        terminal_i = int(keychain.split("terminals[")[-1].split("]")[0])
                        terminal_data = connection_data["terminals"][terminal_i]
                        attr = keychain.split(".")[-1]
                        terminal_data[attr] = value
                    elif "bandwidth" in keychain:
                        bandwidth_data = connection_data["bandwidth"]
                        attr = keychain.split(".")[-1]
                        bandwidth_data[attr] = value
        elif ask == "maximum-bandwidth":
            # FIXME: make bandwidth more realistic; e.g. lookup src & dst and take min of port cap
            answer["results"].append(
                {"bandwidth": "1000000", "name": query["options"][0]["name"]}
            )
        response["queries"].append(answer)

    # Update service instance
    lock.acquire()
    services[instance_uuid].intent.update(intent)
    services[instance_uuid].alias = new_intent.get("alias", "")
    lock.release()

    return response

@nonsense.put("/api/instance/{instance_uuid}/{action}")
def affect_instance(instance_uuid: str, action: str):
    if action == "provision" or action == "reprovision":
        # Retrieve service instance
        service = services[instance_uuid]
        print(service.intent)
        connection_data = service.intent["connections"][0]
        src_root_uri = connection_data["terminals"][0]["uri"]
        dst_root_uri = connection_data["terminals"][1]["uri"]
        # Retrieve RSE names
        with open("config.yaml", "r") as f_in:
            config = yaml.safe_load(f_in).get("nonsense", {})
        src_rse_name = ""
        dst_rse_name = ""
        for site_info in config.get("sites", []):
            if src_rse_name != "" and dst_rse_name != "":
                break
            if src_root_uri == site_info["root_uri"]:
                src_rse_name = site_info["name"]
            if dst_root_uri == site_info["root_uri"]:
                dst_rse_name = site_info["name"]
        # Send packaged data to PSNet
        package = {
            "nonsense_id": service.alias,
            "bandwidth": float(connection_data["bandwidth"]["capacity"])
        }
        # TODO: add requests.put to PSNet
        lock.acquire()
        services[instance_uuid].status = "CREATE - READY"
        lock.release()
    elif action == "cancel":
        lock.acquire()
        services[instance_uuid].status = "CANCEL - READY"
        lock.release()

@nonsense.get("/api/instance/{instance_uuid}/status", response_class=PlainTextResponse)
def check_instance(instance_uuid: str):
    return services[instance_uuid].status

@nonsense.delete("/api/instance/{instance_uuid}")
def delete_instance(instance_uuid: str):
    return

@nonsense.get("/api/discover/lookup/{pattern}")
def lookup_name(pattern: str):
    results = []
    for site_info in config.get("sites", []):
        if pattern in site_info["full_uri"]:
            results.append({
                "resource": site_info["full_uri"],
                "name/tag/value": site_info["name"]
            })
    return {"results": results}

@nonsense.get("/api/discover/lookup/{full_uri}/rooturi", response_class=PlainTextResponse)
def full_to_root_uri(full_uri: str):
    root_uri = site_info_lookup("root_uri", full_uri=full_uri)
    print(root_uri)
    if not root_uri:
        raise HTTPException(
            status_code=404,
            detail=f"resource with full URI {full_uri} not found"
        )
    return root_uri

@nonsense.get("/api/discover/{root_uri}/ipv6pool")
def uri_ipv6pool(root_uri: str):
    ipv6_subnet_pool = site_info_lookup("ipv6_subnet_pool", root_uri=root_uri)
    if not ipv6_subnet_pool:
        raise HTTPException(
            status_code=404,
            detail=f"resource with root URI {root_uri} not found"
        )
    return {
        "domain_uri": root_uri,
        "routing": [
            {
                "ipv6_subnet_pool": ipv6_subnet_pool,
                "service_uri": f"{root_uri}:DUMMY_SWITCH:service+rst-ipv6"
            }
        ],
        "domain_name": "n/a"
    }

# @nonsense.route("/api/discover/<root_uri>/peers", methods=["GET"])
@nonsense.get("/api/discover/{root_uri}/peers")
def uri_peers(root_uri: str):
    port_capacity = site_info_lookup("port_capacity", root_uri=root_uri)
    if not port_capacity:
        raise HTTPException(
            status_code=404,
            detail=f"resource with root URI {root_uri} not found"
        )
    return {
        "domain_uri": "urn:ogf:network:ultralight1.org:2013",
        "domain_name": "n/a",
        "peer_points":[
            {
                "port_name": "n/a",
                "port_uri": f"{root_uri}:Port-channel_102",
                "peer_capacity": port_capacity,
                "peer_vlan_pool": "1779-1799,3600-3619,3985-3989",
                "port_vlan_pool": "1779-1799,3600-3619,3985-3989",
                "port_capacity": port_capacity,
                "peer_uri": f"{root_uri}:Port-channel_102"
            }
        ]
    }

if __name__ == "__main__":
    nonsense.run(debug=True)
