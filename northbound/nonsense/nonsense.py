import json
import yaml
import uuid
import os
from flask import Flask, request

nonsense = Flask("NONSENSE")

PROFILE_UUID = ""

def get_profile_uuid():
    global PROFILE_UUID
    if PROFILE_UUID == "":
        with open("config.yaml", "r") as f_in:
            config = yaml.safe_load(f_in).get("nonsense", {})
            PROFILE_UUID = config.get("profile_uuid")

    return PROFILE_UUID

@nonsense.route("/auth", methods=["POST", "GET"])
def authenticate():
    dummy_token = {
        "access_token": uuid.uuid4().hex,
        "expires_in": 300,
        "refresh_expires_in": 1800,
        "refresh_token": uuid.uuid4().hex,
        "token_type": "Bearer",
        "not-before-policy": 1524167859,
        "session_state": str(uuid.uuid4()),
        "scope": "email profile"
    }
    return json.dumps(dummy_token)

@nonsense.route("/api/profile/<profile_uuid>", methods=["POST", "GET"])
def profile(profile_uuid):
    with open(f"profiles/{profile_uuid}.json", "r") as f_in:
        return f_in.read()

@nonsense.route("/api/instance", methods=["GET"])
def create_instance():
    return str(uuid.uuid4())

@nonsense.route("/api/instance/<instance_uuid>", methods=["POST"])
def edit_instance(instance_uuid):
    print("instance POST")
    print(instance_uuid)
    print(request.json)
    # Initialize response
    response = {
        "intent_uuid": str(uuid.uuid4()),
        "queries": []
    }
    # Create a new service instance if necessary
    if not os.path.isfile(f"nonsense/instances/{instance_uuid}.json"):
        profile_uuid = request.json["service_profile_uuid"]
        with open(f"nonsense/profiles/{profile_uuid}.json", "r") as f_in:
            service_profile = json.load(f_in)
            print(json.dumps(service_profile, indent=2))
        with open(f"nonsense/instances/{instance_uuid}.json", "w") as f_out:
            json.dump(service_profile, f_out)
    # Add service instance ID to response
    response["service_uuid"] = instance_uuid
    # Load service instance
    with open(f"nonsense/instances/{instance_uuid}.json", "r") as f_in:
        service_instance = json.load(f_in)
    # Parse queries and edit instance data
    instance_data = service_instance["intent"]["data"]
    if "alias" in request.json.keys():
        instance_data["alias"] = request.json["alias"] # rule ID
    for query in request.json.get("queries", []):
        ask = query["ask"]
        answer = {"asked": ask, "results": []}
        if ask == "edit":
            for option in query["options"]:
                for keychain, value in option.items():
                    connection_i = int(keychain.split("connections[")[-1].split("]")[0])
                    connection_data = instance_data["connections"][connection_i]
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
            answer["results"].append(
                {"bandwidth": "1000000", "name": query["options"][0]["name"]}
            )
        response["queries"].append(answer)
    # Write updated service instance
    with open(f"nonsense/instances/{instance_uuid}.json", "w") as f_out:
        json.dump(service_instance, f_out)
    return json.dumps(response)

@nonsense.route("/api/instance/<instance_uuid>/<action>", methods=["PUT"])
def affect_instance(instance_uuid, action):
    print("instance PUT")
    print(instance_uuid)
    print(action)
    print(request.args)
    # TODO: ping PSNet
    return ""

@nonsense.route("/api/instance/<instance_uuid>/status", methods=["GET"])
def check_instance(instance_uuid):
    return ""

@nonsense.route("/api/discover/lookup/<pattern>", methods=["POST", "GET"])
def lookup(pattern):
    results = []
    with open("config.yaml", "r") as f_in:
        config = yaml.safe_load(f_in).get("nonsense", {})
    for site_info in config.get("sites", []):
        if pattern in site_info["full_uri"]:
            results.append({
                "resource": site_info["full_uri"],
                "name\/tag\/value": site_info["name"]
            })
    return json.dumps({"results": results})

if __name__ == "__main__":
    nonsense.run(debug=True)
