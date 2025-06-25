#!/usr/bin/env python3

import os
import sys
import json
import requests
import openai

# ─── Setup ─────────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("Set OPENAI_API_KEY in your environment")

# MCP server endpoint (override via env if needed)
MCP_URL = os.getenv("MCP_URL", "http://localhost:4000/mcp")

# ─── RPC helper ────────────────────────────────────────────────────────────────
def rpc_call(rpc_method: str, params: dict = None, id_: int = 1):
    payload = {"jsonrpc": "2.0", "method": rpc_method, "id": id_, "params": params or {}}
    resp = requests.post(MCP_URL, json=payload)
    resp.raise_for_status()
    return resp.json()

# ─── Define functions for BIG-IP integration ───────────────────────────────────
functions = [
    {
        "name": "bigip_run_tmsh",
        "description": "Run a TMSH command on F5 BIG-IP and return the output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": { "type": "string", "description": "The tmsh command to execute, e.g. 'show ltm virtual all-properties'" }
            },
            "required": ["command"]
        }
    },
    {
        "name": "bigip_get_virtuals",
        "description": "Retrieve a list of LTM virtual servers from F5 BIG-IP.",
        "parameters": { "type": "object", "properties": {}, "required": [] }
    },
    {
        "name": "bigip_get_pools",
        "description": "List all LTM pools and their members from F5 BIG-IP.",
        "parameters": { "type": "object", "properties": {}, "required": [] }
    }
]

# ─── Entry point ───────────────────────────────────────────────────────────────
def main():
    # Accept the query as a CLI argument
    if len(sys.argv) < 2:
        print("Usage: python ai_llm_client.py \"<BIG-IP query>\"")
        sys.exit(1)
    user_input = sys.argv[1]

    # Build conversation history
    messages = [
        {
            "role": "system",
            "content": (
                "You can call these functions on the MCP server:\n"
                "- bigip_run_tmsh(command): run a TMSH command on BIG-IP.\n"
                "- bigip_get_virtuals(): list LTM virtual servers.\n"
                "- bigip_get_pools(): list all pools and their member names.\n"
                "Pick the function that best matches the user's request."
            )
        },
        { "role": "user", "content": user_input }
    ]

    # 1) Let the model choose the function
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        functions=functions,
        function_call="auto",
        temperature=0,
    )
    msg = response.choices[0].message

    # 2) Execute the chosen function
    if msg.function_call:
        fn_name = msg.function_call.name
        fn_args = json.loads(msg.function_call.arguments)
        # Map 'bigip_run_tmsh' -> 'bigip.run_tmsh', similarly for others
        rpc_method = fn_name.replace("_", ".", 1)
        rpc_resp = rpc_call(rpc_method, fn_args)

        # Determine result or error
        if "error" in rpc_resp:
            err = rpc_resp["error"]
            fn_result = {"error": True, "code": err.get("code"), "message": err.get("message")}        
        else:
            fn_result = rpc_resp.get("result")

        # Append function_call and its result
        messages.append({
            "role": "assistant",
            "content": None,
            "function_call": { "name": fn_name, "arguments": msg.function_call.arguments }
        })
        messages.append({"role": "function", "name": fn_name, "content": json.dumps(fn_result)})

        # 3) Finalize with model response
        final = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
        )
        print(final.choices[0].message.content)
    else:
        # No function call: output direct reply
        print(msg.content)

if __name__ == "__main__":
    main()

