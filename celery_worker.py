from celery import Celery
import os
import openai
from functions import (
    GoHighLevelAPI,
    log,
    validate_request_data
)
import time
import json

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize Celery
celery_app = Celery(
    'conversation_tasks',
    broker=os.getenv('REDIS_URL'),
    backend=os.getenv('REDIS_URL')
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

def wait_for_run_completion(thread_id, run_id):
    """Wait for the Assistant run to complete and return the final status"""
    while True:
        try:
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id
            )
            if run.status in ['completed', 'failed', 'expired', 'cancelled']:
                return run
            time.sleep(1)
        except Exception as e:
            log("error", f"Error checking run status: {str(e)}")
            return None

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_conversation(self, request_data):
    """
    Celery task to process conversation requests asynchronously.
    """
    try:
        # Validate request data
        validated_fields = validate_request_data(request_data)
        if not validated_fields:
            return {"error": "Invalid request data"}, 400

        thread_id = validated_fields['thread_id']
        assistant_id = validated_fields['assistant_id']
        ghl_contact_id = validated_fields['ghl_contact_id']
        recent_message = validated_fields['ghl_recent_message']

        try:
            # Add message to thread
            openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=recent_message
            )

            # Create and run the assistant
            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            # Wait for completion
            final_run = wait_for_run_completion(thread_id, run.id)
            if not final_run or final_run.status != 'completed':
                raise Exception(f"Run failed or expired: {final_run.status if final_run else 'Unknown'}")

            # Get assistant's response
            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            latest_msg = next((msg for msg in messages.data if msg.role == "assistant"), None)
            
            if not latest_msg:
                raise Exception("No assistant response found")

            response_content = latest_msg.content[0].text.value

            return {
                "status": "success",
                "ghl_contact_id": ghl_contact_id,
                "response": response_content
            }, 200

        except Exception as api_error:
            log("error", f"OpenAI API error: {str(api_error)}", 
                contact_id=ghl_contact_id,
                thread_id=thread_id)
            raise api_error

    except Exception as e:
        log("error", f"Error processing conversation: {str(e)}", 
            contact_id=request_data.get('ghl_contact_id'),
            thread_id=request_data.get('thread_id'),
            retry_count=self.request.retries)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {"error": str(e)}, 500
