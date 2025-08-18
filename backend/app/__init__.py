"""Package initialization for Oracle SQL Assistant API"""

__version__ = "1.0.0"

# Keep package init side‑effect free (avoid importing app/main here)
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
