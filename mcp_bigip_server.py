#!/usr/bin/env python3

from flask import Flask, request, jsonify
import requests, urllib3

# Suppress TLS warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

@app.route("/mcp", methods=["POST"])
def mcp():
    req    = request.get_json()
    method = req.get("method")
    id_    = req.get("id")

    # 1) List available services
    if method == "mcp.list_services":
        return jsonify({"jsonrpc":"2.0","id":id_,"result":["bigip"]})

    # 2) Run arbitrary TMSH
    if method == "bigip.run_tmsh":
        params   = req.get("params", {})
        host     = params.get("host")
        user     = params.get("username")
        password = params.get("password")
        cmd      = params.get("command")
        if not all([host, user, password, cmd]):
            return jsonify({
                "jsonrpc":"2.0","id":id_,
                "error":{"code":-32602,"message":"`host`, `username`, `password`, and `command` are required."}
            })
        url     = f"https://{host}/mgmt/tm/util/bash"
        payload = {"command":"run", "utilCmdArgs":f"-c '{cmd}'"}
        try:
            r = requests.post(url, json=payload,
                              auth=(user, password),
                              verify=False)
            r.raise_for_status()
            out = r.json().get("commandResult", "")
            return jsonify({"jsonrpc":"2.0","id":id_,"result":{"output":out}})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # 3) List virtual servers
    if method == "bigip.get_virtuals":
        params   = req.get("params", {})
        host     = params.get("host")
        user     = params.get("username")
        password = params.get("password")
        if not all([host, user, password]):
            return jsonify({
                "jsonrpc":"2.0","id":id_,
                "error":{"code":-32602,"message":"`host`, `username`, and `password` are required."}
            })
        url = f"https://{host}/mgmt/tm/ltm/virtual?expandSubcollections=true"
        try:
            r = requests.get(url,
                             auth=(user, password),
                             verify=False)
            r.raise_for_status()
            items = r.json().get("items", [])
            vs = [{"name":v["name"], "destination":v["destination"]} for v in items]
            return jsonify({"jsonrpc":"2.0","id":id_,"result":vs})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # 4) List pools and their members
    if method == "bigip.get_pools":
        params   = req.get("params", {})
        host     = params.get("host")
        user     = params.get("username")
        password = params.get("password")
        if not all([host, user, password]):
            return jsonify({
                "jsonrpc":"2.0","id":id_,
                "error":{"code":-32602,"message":"`host`, `username`, and `password` are required."}
            })
        pool_url = f"https://{host}/mgmt/tm/ltm/pool?expandSubcollections=true"
        try:
            resp  = requests.get(pool_url,
                                 auth=(user, password),
                                 verify=False)
            resp.raise_for_status()
            pools = resp.json().get("items", [])
            result = []
            for p in pools:
                name    = p.get("name")
                members = []
                members_url = f"https://{host}/mgmt/tm/ltm/pool/{name}/members"
                mresp = requests.get(members_url,
                                     auth=(user, password),
                                     verify=False)
                if mresp.ok:
                    for mi in mresp.json().get("items", []):
                        members.append(mi.get("name"))
                result.append({"pool": name, "members": members})
            return jsonify({"jsonrpc":"2.0","id":id_,"result":result})
        except Exception as e:
            return jsonify({"jsonrpc":"2.0","id":id_,"error":{"code":-32000,"message":str(e)}})

    # 5) Unknown method
    return jsonify({
        "jsonrpc":"2.0","id":id_,
        "error":{"code":-32601,"message":f"Unknown method {method}"}
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)

