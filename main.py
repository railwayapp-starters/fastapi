import traceback
from redis import Redis
import os
import json
import requests

def log(level, msg, **kwargs):
    """Centralized logger for structured JSON logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))

def validate_request_data(data):
    """
    Validate request data, ensure required fields are present, and handle conversation ID retrieval.
    Returns validated fields dictionary or None if validation fails.
    """
    required_fields = ["thread_id", "assistant_id", "ghl_contact_id", "ghl_recent_message"]
    fields = {field: data.get(field) for field in required_fields}
    fields["ghl_convo_id"] = data.get("ghl_convo_id")

    missing_fields = [field for field in required_fields if not fields[field] or fields[field] in ["", "null", None]]
    if missing_fields:
        log("error", f"Validation -- Missing {', '.join(missing_fields)} -- {fields['ghl_contact_id']}",
            ghl_contact_id=fields["ghl_contact_id"], scope="Validation", received_fields=fields)
        return None

    if not fields["ghl_convo_id"] or fields["ghl_convo_id"] in ["", "null"]:
        ghl_api = GoHighLevelAPI(location_id=os.getenv('GHL_LOCATION_ID', ''))
        fields["ghl_convo_id"] = ghl_api.get_conversation_id(fields["ghl_contact_id"])
        if not fields["ghl_convo_id"]:
            return None

    return fields

class GoHighLevelAPI:
    BASE_URL = "https://services.leadconnectorhq.com"
    HEADERS = {
        "Version": "2021-04-15",
        "Accept": "application/json"
    }

    def __init__(self, location_id):
        self.location_id = location_id

    def get_conversation_id(self, contact_id):
        """Retrieve conversation ID from GHL API."""
        token = fetch_ghl_access_token()
        if not token:
            log("error", "Get convo ID -- Token fetch failed", contact_id=contact_id)
            return None

        url = f"{self.BASE_URL}/conversations/search"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}
        params = {"locationId": self.location_id, "contactId": contact_id}

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log("error", "Get convo ID API call failed", contact_id=contact_id,
                status_code=response.status_code, response=response.text)
            return None

        conversations = response.json().get("conversations", [])
        if not conversations:
            log("error", "No Convo ID found", contact_id=contact_id, response=response.text)
            return None

        return conversations[0].get("id")

    def retrieve_messages(self, convo_id, contact_id):
        """Retrieve messages from GHL API."""
        token = fetch_ghl_access_token()
        if not token:
            log("error", "Retrieve Messages -- Token fetch failed", contact_id=contact_id)
            return []

        url = f"{self.BASE_URL}/conversations/{convo_id}/messages"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            log("error", "Retrieve Messages -- API Call Failed",
                contact_id=contact_id, convo_id=convo_id,
                status_code=response.status_code, response=response.text)
            return []

        messages = response.json().get("messages", {}).get("messages", [])
        if not messages:
            log("error", "Retrieve Messages -- No messages found", contact_id=contact_id,
                convo_id=convo_id, api_response=response.json())
            return []

        return messages

    def update_contact(self, contact_id, update_data):
        """Update contact information in GHL API."""
        token = fetch_ghl_access_token()
        if not token:
            log("error", "Update Contact -- Token fetch failed", contact_id=contact_id)
            return None

        url = f"{self.BASE_URL}/contacts/{contact_id}"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}

        response = requests.put(url, headers=headers, json=update_data)
        if response.status_code != 200:
            log("error", "Update Contact -- API Call Failed", contact_id=contact_id,
                status_code=response.status_code, response=response.text)
            return None

        log("info", "Update Contact -- Successfully updated", contact_id=contact_id, response=response.json())
        return response.json()

def fetch_ghl_access_token():
    """Fetch current GHL access token from Railway."""
    query = f"""
    query {{
      variables(
        projectId: "{os.getenv('RAILWAY_PROJECT_ID')}"
        environmentId: "{os.getenv('RAILWAY_ENVIRONMENT_ID')}"
        serviceId: "{os.getenv('RAILWAY_SERVICE_ID')}"
      )
    }}
    """
    try:
        response = requests.post(
            "https://backboard.railway.app/graphql/v2",
            headers={
                "Authorization": f"Bearer {os.getenv('RAILWAY_API_TOKEN')}", 
                "Content-Type": "application/json"
            },
            json={"query": query}
        )
        if response.status_code == 200:
            response_data = response.json()
            if response_data and 'data' in response_data and response_data['data']:
                variables = response_data['data'].get('variables', {})
                if variables and 'GHL_ACCESS' in variables:
                    return variables['GHL_ACCESS']
        log("error", f"GHL Access -- Failed to fetch token", 
            scope="GHL Access", status_code=response.status_code, 
            response=response.text)
    except Exception as e:
        log("error", f"GHL Access -- Request failed", 
            scope="GHL Access", error=str(e), 
            traceback=traceback.format_exc())
    return None
