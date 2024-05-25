from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from datetime import datetime
import requests
import json
import logging

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class LoginRequest(BaseModel):
    Username: str
    Password: str

class UserAccount(BaseModel):
    user_id: int
    account_id: int

class OrderRequest(BaseModel):
    symbol: str
    quantity: int
    price: float
    stop_price: float
    expire_date: str  # This will be passed in mm/dd/yyyy format
    side: str = "Buy"
    order_type: str = "Market"
    time_in_force: str = "Day"
    comment: str = "Placing a test order"

    # @validator('expire_date')
    # def validate_expire_date(cls, v):
    #     try:
    #         # Parse the date from mm/dd/yyyy format
    #         date = datetime.strptime(v, "%m/%d/%Y")
    #         # Convert to ISO 8601 format with a fixed time
    #         return date.strftime("%Y-%m-%dT18:12:25.740Z")
    #     except ValueError:
    #         raise ValueError("ExpireDate must be in mm/dd/yyyy format")

class AuthState:
    token: str = None
    user_id: int = None
    account_id: int = None

auth_state = AuthState()

@app.post("/token")
async def get_token(Username: str = Header(None), Password: str = Header(None)):
    url = "https://pub-api-ttg-demo-prod.etnasoft.us/api/token"
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        "Username": Username,
        "Password": Password,
        'Et-App-Key': 'ODJlMTYwYjQtYjUyNS00ZjNmLTg0NmEtOGExYjFhMWNjOTcy'
    }

    # Log the request details
    logger.debug(f"Request URL: {url}")
    logger.debug(f"Request Headers: {headers}")

    response = requests.post(url, headers=headers)

    # Log the response details
    logger.debug(f"Response Status Code: {response.status_code}")
    logger.debug(f"Response Text: {response.text}")

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    response_data = response.json()
    auth_state.token = response_data.get("Token")

    if not auth_state.token:
        raise HTTPException(status_code=401, detail="Authentication failed")

    return {"token": auth_state.token}

@app.post("/set_user_account")
async def set_user_account(user_account: UserAccount):
    auth_state.user_id = user_account.user_id
    auth_state.account_id = user_account.account_id
    return {"message": "User ID and Account ID set successfully"}

@app.post("/place_order/")
async def place_order(order: OrderRequest):
    if not auth_state.token:
        raise HTTPException(status_code=401, detail="Authentication token is missing")
    
    if not auth_state.user_id or not auth_state.account_id:
        raise HTTPException(status_code=400, detail="User ID and Account ID must be set before placing an order")

    api_version = "1.0"
    base_url = f"https://pub-api-ttg-demo-prod.etnasoft.us/api"
    url = f"{base_url}/v{api_version}/accounts/{auth_state.account_id}/orders"

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {auth_state.token}',
        'Et-App-Key': 'ODJlMTYwYjQtYjUyNS00ZjNmLTg0NmEtOGExYjFhMWNjOTcy'
    }

    order_payload = {
        "Symbol": order.symbol,
        "ExpireDate": order.expire_date,
        "Type": order.order_type,
        "Side": order.side,
        "Comment": order.comment,
        "ExecInst": "None",
        "TimeInforce": order.time_in_force,
        "Quantity": order.quantity,
        "Price": order.price,
        "StopPrice": order.stop_price,
        "ParentId": 0
    }

    response = requests.post(url, headers=headers, data=json.dumps(order_payload))

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    
    return response.json()
