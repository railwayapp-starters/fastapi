from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import traceback


app = FastAPI()

@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}

def log(level, msg, **kwargs):
    """Centralized logger for structured JSON logging."""
    kwargs['state'] = str(kwargs.get('state', {}))
    print(json.dumps({"level": level, "msg": msg, **kwargs}))



@app.post("/testEndpoint")
async def test_endpoint(request: Request):
    try:
        data = await request.json()
        log("info", "Received request parameters", **{
            k: data.get(k) for k in [
                "thread_id", "assistant_id", "ghl_contact_id", 
                "ghl_recent_message", "ghl_convo_id"
            ]
        })
        return JSONResponse(
            content={
                "response_type": "action, message, message_action",
                "action": {
                    "type": "force end, handoff, add_contact_id",
                    "details": {
                        "ghl_convo_id": "afdlja;ldf"
                    }
                },
                "message": "wwwwww",
                "error": "booo error"
            },
            status_code=200
        )
    except Exception as e:
        log("error", f"Unexpected error: {str(e)}", traceback=traceback.format_exc())
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)
