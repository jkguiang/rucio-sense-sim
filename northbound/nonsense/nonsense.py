import json
import uuid
from flask import Flask, request

nonsense = Flask("NONSENSE")

@nonsense.route("/auth", methods=["POST", "GET"])
def authenticate():
    print(request.form)
    print(request.headers)
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
    print(dummy_token)
    return json.dumps(dummy_token)

@nonsense.route("/api/profile/<profile_uuid>", methods=["POST", "GET"])
def profile(profile_uuid):
    print("profile")
    print(profile_uuid)
    print(request.form)
    print(request.headers)
    return ""

@nonsense.route("/api/instance", methods=["GET"])
@nonsense.route("/api/instance/<instance_uuid>", methods=["POST"])
@nonsense.route("/api/instance/<instance_uuid>/<action>", methods=["PUT"])
def instance(instance_uuid=None, action=None):
    if request.method == "GET":
        return str(uuid.uuid4())
    elif request.method == "POST":
        print("post instance")
        print(instance_uuid)
        print(request.json)
    elif request.method == "PUT":
        print("put instance")
        print(instance_uuid)
        print(action)
        print(request.args)
    return ""

@nonsense.route("/api/discover/lookup/<name>", methods=["POST", "GET"])
def lookup(name):
    print("lookup")
    return ""

if __name__ == "__main__":
    nonsense.run(debug=True)
