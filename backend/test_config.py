import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test the API request configuration
api_request_timeout = int(os.getenv("API_REQUEST_TIMEOUT", "60"))
api_max_retries = int(os.getenv("API_MAX_RETRIES", "2"))
api_retry_delay = float(os.getenv("API_RETRY_DELAY", "2.0"))

print("API Request Configuration:")
print(f"  Timeout: {api_request_timeout} seconds")
print(f"  Max Retries: {api_max_retries}")
print(f"  Retry Delay: {api_retry_delay} seconds")