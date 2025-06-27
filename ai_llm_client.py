#!/usr/bin/env python3

import os
import sys
import json
import requests
import openai
from dotenv import load_dotenv

# ─── Load environment variables ─────────────────────────────────────────────────
load_dotenv()

# ─── Setup ─────────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("Set OPENAI_API_KEY in your .env or environment")

# MCP server endpoint (override via env if needed)
MCP_URL = os.getenv("MCP_URL", "http://localhost:4000/mcp")

# BIG-IP credentials from .env or env vars
BIGIP_HOST = os.getenv("BIGIP_HOST")
BIGIP_USER = os.getenv("BIGIP_USER")
BIGIP_PASS = os.getenv("BIGIP_PASS")
if not (BIGIP_HOST and BIGIP_USER and BIGIP_PASS):
    raise RuntimeError("Set BIGIP_HOST, BIGIP_USER, and BIGIP_PASS in your .env or environment")

# ─── RPC helper ────────────────────────────────────────────────────────────────
def rpc_call(rpc_method: str, params: dict = None, id_: int = 1):
    payload = {"jsonrpc": "2.0", "method": rpc_method, "id": id_, "params": params or {}}
    resp = requests.post(MCP_URL, json=payload)
    resp.raise_for_status()
    return resp.json()

# ─── Define Functions for BIG-IP integration ───────────────────────────────────
functions = [
    {
        "name": "bigip_run_tmsh",
        "description": "Run a TMSH command on F5 BIG-IP and return the output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "TMSH command to execute, e.g., 'show ltm virtual all-properties'"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "bigip_get_virtuals",
        "description": "Retrieve a list of LTM virtual servers from F5 BIG-IP.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "bigip_get_pools",
        "description": "List all LTM pools and their members from F5 BIG-IP.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }
]

# ─── Entry point ───────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python ai_llm_client.py \"<BIG-IP query>\"")
        sys.exit(1)
    user_input = sys.argv[1]

    messages = [
        {
            "role": "system",
            "content": (
                "Available functions on MCP server:\n"
                "- bigip_run_tmsh(command): run a TMSH command on BIG-IP.\n"
                "- bigip_get_virtuals(): list virtual servers.\n"
                "- bigip_get_pools(): list pools and their members.\n"
                "Provide the appropriate function call to answer the user's request."
            )
        },
        {"role": "user", "content": user_input}
    ]

    # 1) Ask model to select function
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        functions=functions,
        function_call="auto",
        temperature=0
    )
    msg = response.choices[0].message

    # 2) Execute function call if present
    if msg.function_call:
        fn_name = msg.function_call.name
        fn_args = json.loads(msg.function_call.arguments)

        # Inject BIG-IP credentials
        fn_args.update({
            "host": BIGIP_HOST,
            "username": BIGIP_USER,
            "password": BIGIP_PASS
        })

        rpc_method = fn_name.replace("_", ".", 1)
        rpc_resp = rpc_call(rpc_method, fn_args)

        if "error" in rpc_resp:
            err = rpc_resp["error"]
            fn_result = {"error": True, "code": err.get("code"), "message": err.get("message")}        
        else:
            fn_result = rpc_resp.get("result")

        # Append function call and result
        messages.append({
            "role": "assistant",
            "content": None,
            "function_call": {"name": fn_name, "arguments": json.dumps(fn_args)}
        })
        messages.append({"role": "function", "name": fn_name, "content": json.dumps(fn_result)})

        # 3) Get final human-readable answer
        final = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0
        )
        print(final.choices[0].message.content)
    else:
        print(msg.content)

if __name__ == "__main__":
    main()

