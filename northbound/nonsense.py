import json
import yaml
import uuid
import requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

nonsense = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth")

services = {}

with open("config.yaml", "r") as config_yaml:
    config = yaml.safe_load(config_yaml)
    nonsense_config = config.get("nonsense")
    vsnet_config = config.get("vsnet")

vsnet_url = f"{vsnet_config.get('host')}:{vsnet_config.get('port')}"
profile_uuid = nonsense_config.get("profile_uuid")

class Service:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.alias = ""
        self.intent = {}
        self.status = ""

def site_info_lookup(key, root_uri="", full_uri="", name=""):
    for site_info in nonsense_config.get("sites", []):
        if name and name == site_info["name"]:
            return site_info.get(key, None)
        elif root_uri and root_uri == site_info["root_uri"]:
            return site_info.get(key, None)
        elif full_uri and full_uri == site_info["full_uri"]:
            return site_info.get(key, None)

@nonsense.post("/auth")
async def authenticate(form_data: OAuth2PasswordRequestForm = Depends()):
    return {"access_token": form_data.username, "token_type": "Bearer"}

@nonsense.get("/api/profile/{profile_uuid}")
def profile(profile_uuid: str):
    with open(f"northbound/profiles/{profile_uuid}.json", "r") as profile_json:
        return profile_json.read()

@nonsense.delete("/api/service/{instance_uuid}")
def delete_service(instance_uuid: str):
    return

@nonsense.get("/api/instance", response_class=PlainTextResponse)
def create_instance():
    service = Service()
    services[service.id] = service
    return service.id

@nonsense.post("/api/instance/{instance_uuid}")
def query_instance(instance_uuid: str, new_intent: dict):
    # Initialize response
    response = {
        "service_uuid": instance_uuid,
        "intent_uuid": str(uuid.uuid4()),
        "queries": []
    }

    # Load service profile
    with open(f"northbound/profiles/{profile_uuid}.json", "r") as profile_json:
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
            # TODO: make max bandwidth more realistic
            answer["results"].append(
                {"bandwidth": "1000000", "name": query["options"][0]["name"]}
            )

        response["queries"].append(answer)

    # Update service instance
    services[instance_uuid].intent.update(intent)
    services[instance_uuid].alias = new_intent.get("alias", "")

    return response

@nonsense.put("/api/instance/{instance_uuid}/{action}")
def affect_instance(instance_uuid: str, action: str):
    if action == "provision" or action == "reprovision":
        # Retrieve service instance
        service = services[instance_uuid]
        connection_data = service.intent["connections"][0]
        src_root_uri = connection_data["terminals"][0]["uri"]
        dst_root_uri = connection_data["terminals"][1]["uri"]
        # Retrieve RSE names
        src_rse_name = site_info_lookup("name", root_uri=src_root_uri)
        if not src_rse_name:
            raise HTTPException(
                status_code=404,
                detail=f"resource with root URI {src_root_uri} not found"
            )
        dst_rse_name = site_info_lookup("name", root_uri=dst_root_uri)
        if not dst_rse_name:
            raise HTTPException(
                status_code=404,
                detail=f"resource with root URI {dst_root_uri} not found"
            )
        # Send data to VSNet
        requests.put(
            f"http://{vsnet_url}/connections/{service.alias}/update", 
            params={"bandwidth": float(connection_data["bandwidth"]["capacity"])}
        )
        services[instance_uuid].status = "CREATE - READY"
    elif action == "cancel":
        services[instance_uuid].status = "CANCEL - READY"

@nonsense.get("/api/instance/{instance_uuid}/status", response_class=PlainTextResponse)
def check_instance(instance_uuid: str):
    return services[instance_uuid].status

@nonsense.delete("/api/instance/{instance_uuid}")
def delete_instance(instance_uuid: str):
    return

@nonsense.get("/api/discover/lookup/{pattern}")
def lookup_name(pattern: str):
    results = []
    for site_info in nonsense_config.get("sites", []):
        if pattern in site_info["full_uri"]:
            results.append({
                "resource": site_info["full_uri"],
                "name/tag/value": site_info["name"]
            })
    return {"results": results}

@nonsense.get("/api/discover/lookup/{full_uri}/rooturi", response_class=PlainTextResponse)
def full_to_root_uri(full_uri: str):
    root_uri = site_info_lookup("root_uri", full_uri=full_uri)
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
