#!/usr/bin/env python3

from flask import Flask, request, jsonify
import os, requests, urllib3

# Suppress TLS warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# BIG-IP credentials (override via env vars if needed)
BIGIP_HOST = os.getenv("BIGIP_HOST", "172.16.60.106")
BIGIP_USER = os.getenv("BIGIP_USER", "admin")
BIGIP_PASS = os.getenv("BIGIP_PASS", "password")

@app.route("/mcp", methods=["POST"])
def mcp():
    req = request.get_json()
    method = req.get("method")
    id_ = req.get("id")

    # List services
    if method == "mcp.list_services":
        return jsonify({"jsonrpc": "2.0", "id": id_, "result": ["bigip"]})

    # Run arbitrary TMSH
    if method == "bigip.run_tmsh":
        params = req.get("params", {})
        cmd = params.get("command")
        if not cmd:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32602,"message":"`command` is required"}})
        url = f"https://{BIGIP_HOST}/mgmt/tm/util/bash"
        payload = {"command":"run", "utilCmdArgs":f"-c '{cmd}'"}
        try:
            r = requests.post(url, json=payload, auth=(BIGIP_USER,BIGIP_PASS), verify=False)
            r.raise_for_status()
            out = r.json().get("commandResult","")
            return jsonify({"jsonrpc":"2.0","id":id_,"result":{"output":out}})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # List virtual servers
    if method == "bigip.get_virtuals":
        url = f"https://{BIGIP_HOST}/mgmt/tm/ltm/virtual?expandSubcollections=true"
        try:
            r = requests.get(url, auth=(BIGIP_USER,BIGIP_PASS), verify=False)
            r.raise_for_status()
            items = r.json().get("items", [])
            vs = [{"name":v.get("name"),"destination":v.get("destination")} for v in items]
            return jsonify({"jsonrpc":"2.0","id":id_,"result":vs})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # List pools and members
    if method == "bigip.get_pools":
        # Fetch pool list
        pool_url = f"https://{BIGIP_HOST}/mgmt/tm/ltm/pool?expandSubcollections=true"
        try:
            resp = requests.get(pool_url, auth=(BIGIP_USER,BIGIP_PASS), verify=False)
            resp.raise_for_status()
            pools = resp.json().get("items", [])
            result = []
            for p in pools:
                pool_name = p.get("name")
                members = []
                # subcollection of members
                for m in p.get("membersReference", {}).get("linkContext", []):
                    pass
                # instead, fetch pool members stats from stats endpoint
                stats_url = f"https://{BIGIP_HOST}/mgmt/tm/ltm/pool/{pool_name}/members"
                mresp = requests.get(stats_url, auth=(BIGIP_USER,BIGIP_PASS), verify=False)
                if mresp.ok:
                    mitems = mresp.json().get("items", [])
                    for mi in mitems:
                        members.append(mi.get("name"))
                result.append({"pool": pool_name, "members": members})
            return jsonify({"jsonrpc":"2.0","id":id_,"result":result})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # Unknown method
    return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32601,"message":f"Unknown method {method}"}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)

