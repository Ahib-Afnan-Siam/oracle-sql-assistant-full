import sys
import os

# Set the working directory to the backend directory
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)

# Add the current directory to Python path
sys.path.insert(0, backend_dir)

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# Import and run the application
from app.main import app
import uvicorn

if __name__ == "__main__":
    print("Starting Oracle SQL Assistant server...")
    print("JWT configuration loaded from .env file.")
    
    # For production deployment, bind to all interfaces
    # Set host to "0.0.0.0" to accept connections from any IP
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")