# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
import asyncio
import aioredis
import json
import os
from typing import Dict, Optional
from datetime import datetime
from functions import (
    validate_request_data,
    fetch_ghl_access_token,
    log,
    GoHighLevelAPI,
    OpenAIAPI
)

app = FastAPI()

async def init_redis():
    """Initialize Redis with connection handling."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable is required")
        
    try:
        redis_client = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        await redis_client.ping()
        return redis_client
    except Exception as e:
        log("error", "Redis connection failed", error=str(e))
        raise

@app.on_event("startup")
async def startup_event():
    """Initialize app state on startup."""
    try:
        app.state.redis = await init_redis()
        app.state.conversation_queues: Dict[str, asyncio.Queue] = {}
        app.state.processing_locks: Dict[str, asyncio.Lock] = {}
        app.state.openai_api = OpenAIAPI()
        app.state.ghl_api = GoHighLevelAPI(location_id=os.getenv("GHL_LOCATION_ID"))
        
        log("info", "Application started successfully", 
            redis_connected=True,
            apis_initialized=True)
    except Exception as e:
        log("error", "Startup failed", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await app.state.openai_api.close()
    await app.state.ghl_api.close()
    await app.state.redis.close()

async def get_conversation_queue(contact_id: str) -> asyncio.Queue:
    """Get or create a queue for a specific contact."""
    if contact_id not in app.state.conversation_queues:
        app.state.conversation_queues[contact_id] = asyncio.Queue()
    return app.state.conversation_queues[contact_id]

async def get_processing_lock(contact_id: str) -> asyncio.Lock:
    """Get or create a processing lock for a specific contact."""
    if contact_id not in app.state.processing_locks:
        app.state.processing_locks[contact_id] = asyncio.Lock()
    return app.state.processing_locks[contact_id]

@app.post("/triggerResponse")
async def trigger_response(request: Request):
    """Handle incoming webhook from GoHighLevel."""
    try:
        request_data = await request.json()
        
        # Extract message content and create thread if needed
        messages = request_data.get("messages", [])
        if messages:
            thread_response = await app.state.openai_api.create_thread(messages)
            if thread_response:
                request_data["thread_id"] = thread_response["id"]

        validated_fields = await validate_request_data(request_data)
        if not validated_fields:
            return JSONResponse(content={"error": "Invalid request data"}, status_code=400)

        # Add to Redis with TTL
        contact_id = validated_fields["ghl_contact_id"]
        redis_key = f"contact:{contact_id}"
        
        result = await app.state.redis.hset(redis_key, mapping=validated_fields)
        await app.state.redis.expire(redis_key, 30)

        # Add to processing queue
        queue = await get_conversation_queue(contact_id)
        await queue.put(validated_fields)

        if result:
            log("info", f"Redis Queue --- Time Delay Started --- {contact_id}",
                scope="Redis Queue", 
                num_fields_added=result,
                fields_added=json.dumps(validated_fields),
                ghl_contact_id=contact_id)
        else:
            log("info", f"Redis Queue --- Time Delay Reset --- {contact_id}",
                scope="Redis Queue", 
                num_fields_added=result,
                fields_added=json.dumps(validated_fields),
                ghl_contact_id=contact_id)

        # Start processing task
        asyncio.create_task(process_conversation_queue(contact_id))

        return JSONResponse(
            content={
                "message": "Response queued", 
                "ghl_contact_id": contact_id
            },
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
        
        # Start processing task
        asyncio.create_task(process_conversation_queue(contact_id))
        
        return JSONResponse(
            content={
                "message": "Request queued for processing", 
                "ghl_contact_id": contact_id
            },
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
        # Get required fields
        thread_id = request_data.get("thread_id")
        assistant_id = request_data.get("assistant_id")
        
        if not thread_id or not assistant_id:
            raise ValueError("Missing thread_id or assistant_id")
            
        # Process with OpenAI Assistant
        # Add your OpenAI processing logic here
        return {
            "message": "Processed by assistant",
            "thread_id": thread_id
        }
        
    except Exception as e:
        log("error", "Assistant processing error", 
            error=str(e),
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
        log("error", "GHL update error", 
            error=str(e),
            traceback=traceback.format_exc())

@app.post("/testEndpoint")
async def test_endpoint(request: Request):
    """Test endpoint for debugging and monitoring."""
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
