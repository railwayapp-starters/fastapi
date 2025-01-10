from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
from redis import asyncio as aioredis
import os
import json
import asyncio
from typing import Dict
from functions import (
    validate_request_data,
    fetch_ghl_access_token,
    log,
    GoHighLevelAPI
)

app = FastAPI()

# Simple Redis setup
redis_url = os.getenv("REDIS_URL")
redis_client = Redis.from_url(redis_url, decode_responses=True)

# Queue management
conversation_queues: Dict[str, asyncio.Queue] = {}
processing_locks: Dict[str, asyncio.Lock] = {}

async def get_conversation_queue(contact_id: str) -> asyncio.Queue:
    """Get or create a queue for a specific contact."""
    if contact_id not in conversation_queues:
        conversation_queues[contact_id] = asyncio.Queue()
    return conversation_queues[contact_id]

async def get_processing_lock(contact_id: str) -> asyncio.Lock:
    """Get or create a processing lock for a specific contact."""
    if contact_id not in processing_locks:
        processing_locks[contact_id] = asyncio.Lock()
    return processing_locks[contact_id]

@app.post("/triggerResponse")
async def trigger_response(request: Request):
    try:
        request_data = await request.json()
        validated_fields = await validate_request_data(request_data)

        if not validated_fields:
            return JSONResponse(content={"error": "Invalid request data"}, status_code=400)

        # Add validated fields to Redis with TTL
        redis_key = f"contact:{validated_fields['ghl_contact_id']}"
        result = await redis_client.hset(redis_key, mapping=validated_fields)
        await redis_client.expire(redis_key, 30)

        # Add to queue system
        contact_id = validated_fields["ghl_contact_id"]
        queue = await get_conversation_queue(contact_id)
        await queue.put(validated_fields)

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

        # Start processing task
        asyncio.create_task(process_conversation_queue(contact_id))

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
    Asynchronous endpoint with request queueing for handling conversation flow.
    All requests are accepted and processed in order per contact.
    """
    try:
        request_data = await request.json()
        
        # Basic validation for contact ID
        contact_id = request_data.get("ghl_contact_id")
        if not contact_id:
            return JSONResponse(content={"error": "Missing contact ID"}, status_code=400)
            
        # Get or create queue for this contact
        queue = await get_conversation_queue(contact_id)
        
        # Add request to queue
        await queue.put(request_data)
        log("info", f"Request queued for contact {contact_id}", 
            queue_size=queue.qsize())
        
        # Process the request
        asyncio.create_task(process_conversation_queue(contact_id))
        
        return JSONResponse(
            content={"message": "Request queued for processing", "ghl_contact_id": contact_id},
            status_code=200
        )

    except Exception as e:
        tb_str = traceback.format_exc()
        log("error", "GENERAL -- Unhandled exception in queue processing",
            scope="General", error=str(e), traceback=tb_str)
        return JSONResponse(
            content={"error": str(e), "traceback": tb_str},
            status_code=500
        )

async def process_conversation_queue(contact_id: str):
    """Process queued requests for a specific contact."""
    queue = await get_conversation_queue(contact_id)
    lock = await get_processing_lock(contact_id)
    
    async with lock:
        try:
            while not queue.empty():
                request_data = await queue.get()
                
                # Process the conversation with OpenAI Assistant
                response = await process_assistant_conversation(request_data)
                
                # Update GHL with the response
                if response and not response.get("error"):
                    await update_ghl_conversation(request_data, response)
                
                queue.task_done()
                
        except Exception as e:
            log("error", f"Queue processing error for contact {contact_id}: {str(e)}",
                traceback=traceback.format_exc())

async def process_assistant_conversation(request_data: Dict) -> Dict:
    """Process conversation with OpenAI Assistant."""
    try:
        thread_id = request_data.get("thread_id")
        assistant_id = request_data.get("assistant_id")
        
        if not thread_id or not assistant_id:
            raise ValueError("Missing thread_id or assistant_id")
            
        # Add your OpenAI Assistant processing logic here
        return {
            "message": "Processed by assistant",
            "thread_id": thread_id
        }
        
    except Exception as e:
        log("error", "Assistant processing error", error=str(e),
            traceback=traceback.format_exc())
        return {"error": str(e)}

async def update_ghl_conversation(request_data: Dict, response: Dict):
    """Update GoHighLevel conversation with assistant response."""
    try:
        if response.get("message"):
            contact_id = request_data.get("ghl_contact_id")
            convo_id = request_data.get("ghl_convo_id")
            
            if not contact_id or not convo_id:
                raise ValueError("Missing contact_id or convo_id")
                
            # Add your GHL message update logic here
            pass
    except Exception as e:
        log("error", "GHL update error", error=str(e),
            traceback=traceback.format_exc())

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
                        "ghl_convo_id": data.get("ghl_convo_id", "")
                    }
                },
                "message": "Test response",
                "error": None
            },
            status_code=200
        )
    except Exception as e:
        log("error", f"Unexpected error: {str(e)}", traceback=traceback.format_exc())
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)
