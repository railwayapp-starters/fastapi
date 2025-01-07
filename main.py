from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
from redis import Redis
import os
import json
import openai
from functions import (
    validate_request_data,
    fetch_ghl_access_token,
    log,
    GoHighLevelAPI
)
from celery_worker import process_conversation

app = FastAPI()

# Initialize Redis client
redis_url = os.getenv("REDIS_URL")
redis_client = Redis.from_url(redis_url, decode_responses=True)

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')
client = openai.Client()

@app.post("/triggerResponse")
async def trigger_response(request: Request):
    try:
        request_data = await request.json()
        validated_fields = validate_request_data(request_data)

        if not validated_fields:
            return JSONResponse(content={"error": "Invalid request data"}, status_code=400)

        # Add validated fields to Redis with TTL
        redis_key = f"contact:{validated_fields['ghl_contact_id']}"
        result = redis_client.hset(redis_key, mapping=validated_fields)
        redis_client.expire(redis_key, 30)

        if result:
            log("info", f"Redis Queue --- Time Delay Started --- {validated_fields['ghl_contact_id']}",
                scope="Redis Queue", num_fields_added=result,
                fields_added=json.dumps(validated_fields),
                ghl_contact_id=validated_fields['ghl_contact_id'])
        else:
            log("info", f"Redis Queue --- Time Delay Reset --- {validated_fields['ghl_contact_id']}",
                scope="Redis Queue", num_fields_added=result,
                fields_added=json.dumps(validated_fields),
                ghl_contact_id=validated_fields['ghl_contact_id'])

        return JSONResponse(
            content={"message": "Response queued", "ghl_contact_id": validated_fields['ghl_contact_id']}, 
            status_code=200
        )
    except Exception as e:
        log("error", f"Unexpected error: {str(e)}", traceback=traceback.format_exc())
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)

@app.post("/moveConvoForward")
async def move_convo_forward(request: Request):
    """
    Asynchronous endpoint that uses Celery for request queueing and processing.
    Handles OpenAI Assistant interactions with rate limiting and order preservation per contact.
    """
    try:
        request_data = await request.json()
        
        if not request_data.get("ghl_contact_id"):
            return JSONResponse(content={"error": "Missing contact ID"}, status_code=400)
            
        contact_id = request_data["ghl_contact_id"]
        
        # Check if there's an existing task for this contact
        lock_key = f"processing_lock:{contact_id}"
        if redis_client.exists(lock_key):
            return JSONResponse(
                content={
                    "message": "Request queued - previous request still processing",
                    "status": "queued"
                },
                status_code=202
            )
        
        # Set a processing lock with 10-minute timeout
        redis_client.setex(lock_key, 600, "1")
        
        # Queue the task in Celery
        task = process_conversation.delay(request_data)
        
        log("info", f"OpenAI Assistant task queued for contact {contact_id}", 
            task_id=task.id,
            thread_id=request_data.get('thread_id'))
        
        return JSONResponse(
            content={
                "message": "Request accepted for processing",
                "task_id": task.id,
                "status": "processing"
            },
            status_code=202
        )

    except Exception as e:
        tb_str = traceback.format_exc()
        log("error", "GENERAL -- Unhandled exception in request processing",
            scope="General", error=str(e), traceback=tb_str)
        return JSONResponse(
            content={"error": str(e), "traceback": tb_str},
            status_code=500
        )

@app.get("/taskStatus/{task_id}")
async def get_task_status(task_id: str):
    """Endpoint to check the status of a queued task"""
    try:
        task = process_conversation.AsyncResult(task_id)
        if task.ready():
            if task.successful():
                result = task.get()
                return JSONResponse(content={
                    "status": "completed",
                    "result": result
                })
            else:
                return JSONResponse(content={
                    "status": "failed",
                    "error": str(task.result)
                })
        return JSONResponse(content={"status": "processing"})
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error checking task status: {str(e)}"},
            status_code=500
        )

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
