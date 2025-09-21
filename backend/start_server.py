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
    uvicorn.run(app, host="127.0.0.1", port=8092, log_level="debug")