"""
简单的 FastMCP HTTP 服务器用于测试
使用 FastAPI 实现 MCP HTTP/JSON-RPC 协议
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import asyncio
import uuid

app = FastAPI(title="Test MCP Server")

_TOOLS = [
    {
        "name": "echo",
        "description": "Echo back the input message",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "time",
        "description": "Get current time",
        "inputSchema": {"type": "object", "properties": {}}
    }
]

_request_id = 0

def next_id():
    global _request_id
    _request_id += 1
    return _request_id


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP HTTP/JSON-RPC endpoint"""
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "test-mcp-server",
                    "version": "1.0.0"
                }
            }
        })

    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": _TOOLS}
        })

    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "echo":
            msg = arguments.get("message", "")
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Echo: {msg}"}
                    ]
                }
            })

        elif tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Result: {a + b}"}
                    ]
                }
            })

        elif tool_name == "time":
            from datetime import datetime
            now = datetime.now().isoformat()
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Current time: {now}"}
                    ]
                }
            })

        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            })

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    })


if __name__ == "__main__":
    import uvicorn
    print("Starting Test MCP Server on http://localhost:8000/mcp")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
