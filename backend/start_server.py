import sys
import os

# Set the working directory to the backend directory
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)

# Add the current directory to Python path
sys.path.insert(0, backend_dir)

# Import and run the application
from app.main import app
import uvicorn

if __name__ == "__main__":
    # For production deployment, bind to all interfaces
    # Set host to "0.0.0.0" to accept connections from any IP
    uvicorn.run(app, host="0.0.0.0", port=8095, log_level="info")