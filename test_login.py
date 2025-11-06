import requests
import json

# Test the login endpoint
url = "http://localhost:8095/login"

# Test data with the provided credentials
payload = {
    "username": "ahibafnan99@gmail.com",
    "password": "#ahibsiam99#"
}

headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")