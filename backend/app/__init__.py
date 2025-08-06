"""Package initialization for Oracle SQL Assistant API"""

# Version of the application
__version__ = "1.0.0"

# Import key components to make them easily accessible
from app.main import app  # noqa: F401
from app.embeddings import get_embedding  # noqa: F401
from app.db_connector import connect_vector  # noqa: F401

# Initialize logging configuration
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)