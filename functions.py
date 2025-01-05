def log(level, msg, **kwargs):
    """Centralized logger for structured JSON logging."""
    kwargs['state'] = str(kwargs.get('state', {}))
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
        ghl_api = GoHighLevelAPI(location_id="your_location_id")
        fields["ghl_convo_id"] = ghl_api.get_conversation_id(fields["ghl_contact_id"])
        if not fields["ghl_convo_id"]:
            return None

    log("info", f"Validation -- Fields Received -- {fields['ghl_contact_id']}", scope="Validation", **fields)
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
        token = fetch_ghl_access_token()
        if not token:
            log("error", "Get convo ID -- Token fetch failed", contact_id=contact_id)
            return None

        url = f"{self.BASE_URL}/conversations/search"
        headers = {**self.HEADERS, "Authorization": f"Bearer {token}"}
        params = {"locationId": self.location_id, "contactId": contact_id}

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log("error", "Get convo ID API call failed", contact_id=contact_id, \
                status_code=response.status_code, response=response.text)
            return None

        conversations = response.json().get("conversations", [])
        if not conversations:
            log("error", "No Convo ID found", contact_id=contact_id, response=response.text)
            return None

        return conversations[0].get("id")
