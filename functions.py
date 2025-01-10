import traceback
import aiohttp
import json
import os
from typing import Optional, Dict, List
import aioredis
from datetime import datetime

def log(level: str, msg: str, **kwargs):
    """Centralized logger for structured JSON logging."""
    print(json.dumps({
        "level": level,
        "msg": msg,
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }))

class OpenAIAPI:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "assistants=v2",
            "Content-Type": "application/json"
        }
        self._session = None

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def create_thread(self, messages: List[Dict] = None):
        """Create a new thread with optional initial messages."""
        try:
            session = await self.get_session()
            async with session.post(
                "https://api.openai.com/v1/threads",
                json={"messages": messages} if messages else {}
            ) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                log("error", "Thread creation failed", response=error_text)
                return None
        except Exception as e:
            log("error", "Thread creation error", error=str(e))
            return None

class GoHighLevelAPI:
    BASE_URL = "https://services.leadconnectorhq.com"
    HEADERS = {
        "Version": "2021-04-15",
        "Accept": "application/json"
    }

    def __init__(self, location_id: str):
        self.location_id = location_id
        self._session = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_conversation_id(self, contact_id: str) -> Optional[str]:
        """Retrieve conversation ID from GHL API asynchronously."""
        token = await fetch_ghl_access_token()
        if not token:
            log("error", "Get convo ID -- Token fetch failed", contact_id=contact_id)
            return None

        url = f"{self.BASE_URL}/conversations/search"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}
        params = {"locationId": self.location_id, "contactId": contact_id}

        session = await self.get_session()
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    log("error", "Get convo ID API call failed", contact_id=contact_id,
                        status_code=response.status, response=await response.text())
                    return None

                data = await response.json()
                conversations = data.get("conversations", [])
                if not conversations:
                    log("error", "No Convo ID found", contact_id=contact_id, response=data)
                    return None

                return conversations[0].get("id")
        except Exception as e:
            log("error", "Get convo ID request failed", contact_id=contact_id,
                error=str(e), traceback=traceback.format_exc())
            return None

    async def retrieve_messages(self, convo_id: str, contact_id: str) -> List[Dict]:
        """Retrieve messages from GHL API asynchronously."""
        token = await fetch_ghl_access_token()
        if not token:
            log("error", "Retrieve Messages -- Token fetch failed", contact_id=contact_id)
            return []

        url = f"{self.BASE_URL}/conversations/{convo_id}/messages"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}

        session = await self.get_session()
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    log("error", "Retrieve Messages -- API Call Failed",
                        contact_id=contact_id, convo_id=convo_id,
                        status_code=response.status, response=await response.text())
                    return []

                data = await response.json()
                messages = data.get("messages", {}).get("messages", [])
                if not messages:
                    log("error", "Retrieve Messages -- No messages found",
                        contact_id=contact_id, convo_id=convo_id, api_response=data)
                    return []

                return messages
        except Exception as e:
            log("error", "Retrieve messages request failed",
                contact_id=contact_id, convo_id=convo_id,
                error=str(e), traceback=traceback.format_exc())
            return []

async def fetch_ghl_access_token() -> Optional[str]:
    """Fetch current GHL access token from Railway asynchronously."""
    query = f"""
    query {{
      variables(
        projectId: "{os.getenv('RAILWAY_PROJECT_ID')}"
        environmentId: "{os.getenv('RAILWAY_ENVIRONMENT_ID')}"
        serviceId: "{os.getenv('RAILWAY_SERVICE_ID')}"
      )
    }}
    """
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://backboard.railway.app/graphql/v2",
                headers={
                    "Authorization": f"Bearer {os.getenv('RAILWAY_API_TOKEN')}",
                    "Content-Type": "application/json"
                },
                json={"query": query}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and 'data' in data and data['data']:
                        variables = data['data'].get('variables', {})
                        if variables and 'GHL_ACCESS' in variables:
                            return variables['GHL_ACCESS']
                log("error", "GHL Access -- Failed to fetch token",
                    scope="GHL Access", status_code=response.status,
                    response=await response.text())
        except Exception as e:
            log("error", "GHL Access -- Request failed",
                scope="GHL Access", error=str(e),
                traceback=traceback.format_exc())
        return None

async def validate_request_data(data: dict) -> Optional[dict]:
    """Validate request data and handle conversation ID retrieval."""
    required_fields = ["thread_id", "assistant_id", "ghl_contact_id", "ghl_recent_message"]
    fields = {field: data.get(field) for field in required_fields}
    fields["ghl_convo_id"] = data.get("ghl_convo_id")

    missing_fields = [field for field in required_fields if not fields[field] or fields[field] in ["", "null", None]]
    if missing_fields:
        log("error", f"Validation -- Missing {', '.join(missing_fields)} -- {fields['ghl_contact_id']}",
            ghl_contact_id=fields["ghl_contact_id"], scope="Validation", received_fields=fields)
        return None

    if not fields["ghl_convo_id"] or fields["ghl_convo_id"] in ["", "null"]:
        ghl_api = GoHighLevelAPI(location_id=os.getenv("GHL_LOCATION_ID"))
        fields["ghl_convo_id"] = await ghl_api.get_conversation_id(fields["ghl_contact_id"])
        await ghl_api.close()
        if not fields["ghl_convo_id"]:
            return None

    return fields
