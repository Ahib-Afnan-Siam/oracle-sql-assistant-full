#!/usr/bin/env python3
"""
ERP R12 Initialization Script
"""
import os
import sys
import logging

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.ERP_R12_Test_DB.schema_loader_chroma import load_schema_to_chroma

def setup_logging():
    """Set up logging for the initialization process"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def initialize_erp_r12():
    """Initialize the ERP R12 module"""
    logger = setup_logging()
    logger.info("Starting ERP R12 initialization...")
    
    try:
        # Load schema to ChromaDB
        logger.info("Loading ERP R12 schema to vector store...")
        load_schema_to_chroma()
        logger.info("✅ ERP R12 schema loading completed successfully")
        
        # Additional initialization steps can be added here
        logger.info("✅ ERP R12 initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ ERP R12 initialization failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = initialize_erp_r12()
    sys.exit(0 if success else 1)