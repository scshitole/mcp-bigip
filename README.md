# AI-MCP Client & Server Flow

This repository demonstrates how the AI-powered MCP (Model Context Protocol) client interacts with an MCP server to retrieve pool and member information from an F5 BIG-IP device. Below is a step-by-step explanation of what happens when you run the client:

## Prerequisites

* Python 3.7+
* `openai` Python package
* `requests`, `flask`, `python-dotenv` packages
* A running MCP server (`mcp_bigip_server.py`) on `http://localhost:4000/mcp`
* An F5 BIG-IP device accessible at the configured host, with valid credentials

## Running the AI-MCP Client

```bash
python ai_llm_client.py "List all pools and their members"
```

### 1. Startup & Configuration

* The script reads your `OPENAI_API_KEY` and the `MCP_URL` (defaults to `http://localhost:4000/mcp`) from environment or `.env` file.
* It also loads BIG-IP credentials (`BIGIP_HOST`, `BIGIP_USER`, `BIGIP_PASS`).
* Defines three functions for the model to call:

  * `bigip_run_tmsh`
  * `bigip_get_virtuals`
  * `bigip_get_pools`

### 2. Read Your Query

* Captures the first command-line argument (`"List all pools and their members"`) as the user’s request.

### 3. Build the Initial Chat Prompt

* Adds a **system** message describing the available functions.
* Adds a **user** message containing your actual question.

### 4. Ask the LLM to Pick a Function

* Calls:

  ```python
  openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    functions=functions,
    function_call="auto",
    temperature=0
  )
  ```
* The model responds with a `function_call` payload instead of plain text, for example:

  ```json
  {
    "name": "bigip_get_pools",
    "arguments": "{}"
  }
  ```

### 5. Translate into an MCP RPC

* Detects `msg.function_call.name == "bigip_get_pools"`.
* Maps the function name to the JSON-RPC method by replacing the first underscore with a dot:
  `"bigip_get_pools" → "bigip.get_pools"`.
* Constructs a JSON-RPC 2.0 request:

  ```json
  {
    "jsonrpc": "2.0",
    "method": "bigip.get_pools",
    "id": 1,
    "params": {}
  }
  ```

### 6. Send the RPC to the MCP Server

* The `rpc_call()` helper sends an HTTP POST to `http://localhost:4000/mcp` with the JSON-RPC body.
* The Flask-based MCP server receives the request, calls the F5 REST API under the hood, and returns:

  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "result": [
      { "pool": "pool1", "members": ["10.0.0.1:80","10.0.0.2:80"] },
      { "pool": "pool2", "members": ["10.0.0.3:443"] }
    ]
  }
  ```

### 7. Handle Errors or Extract the Result

* If the JSON-RPC response contains an `error` field, the client wraps it into an error object.
* Otherwise, it extracts the `result` array for further processing.

### 8. Feed Data Back to the LLM

* Appends two messages to the conversation:

  1. An **assistant**-role message indicating the function call.
  2. A **function**-role message whose `content` is the JSON-serialized `result`.
* Calls `openai.chat.completions.create(...)` again (without the `functions` list) to let the model craft the final reply.

### 9. Generate the Human-Readable Answer

* The model uses the pool/member data from context and composes a friendly response, e.g.:

  > Here are your pools and members:
  >
  > * **pool1**: 10.0.0.1:80, 10.0.0.2:80
  > * **pool2**: 10.0.0.3:443

### 10. Print the Reply

* The client script prints the model’s final reply to the terminal.

---

## Summary

1. Client constructs a prompt with user intent and available functions.
2. Model chooses the appropriate function via JSON-RPC semantics.
3. Client sends an MCP RPC to the Flask server.
4. Server interacts with BIG-IP’s REST API and returns structured results.
5. Client re-injects results into the chat.
6. Model generates a human-friendly answer.

This flow enables seamless tool invocation and dynamic data retrieval from network devices using AI-driven orchestration. Feel free to customize or extend the functions for your own use cases.
