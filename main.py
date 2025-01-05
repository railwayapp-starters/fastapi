from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
from redis import Redis
import os
import json
from functions import (
    validate_request_data,
    fetch_ghl_access_token,
    log,
    GoHighLevelAPI
)

app = FastAPI()

redis_url = os.getenv("REDIS_URL")
redis_client = Redis.from_url(redis_url, decode_responses=True)

@app.post("/trigger_response")
async def trigger_response(request: Request):
    try:
        request_data = await request.json()
        validated_fields = validate_request_data(request_data)

        if not validated_fields:
            return JSONResponse(content={"error": "Invalid request data"}, status_code=400)

        # Add validated fields to Redis
        redis_key = f"conversation:{validated_fields['ghl_convo_id']}"
        redis_client.hmset(redis_key, validated_fields)

        return JSONResponse(content={"message": "Data successfully added to Redis", "data": validated_fields}, status_code=200)
    except Exception as e:
        log("error", f"Unexpected error: {str(e)}", traceback=traceback.format_exc())
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)




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
