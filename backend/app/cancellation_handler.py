"""
Cancellation handler for FastAPI applications.
Handles client disconnections and propagates cancellation to long-running operations.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional
from anyio import create_task_group
from fastapi import Request

logger = logging.getLogger(__name__)

class CancellationManager:
    """Manages cancellation tokens for long-running operations."""
    
    def __init__(self):
        self._cancelled = False
        self._callbacks = []
    
    def is_cancelled(self) -> bool:
        """Check if the operation has been cancelled."""
        return self._cancelled
    
    def cancel(self):
        """Cancel the operation and notify all callbacks."""
        if not self._cancelled:
            self._cancelled = True
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.warning(f"Error in cancellation callback: {e}")
    
    def add_callback(self, callback: Callable[[], None]):
        """Add a callback to be called when cancellation occurs."""
        self._callbacks.append(callback)

@asynccontextmanager
async def handle_client_disconnect(request: Request):
    """
    Async context manager that creates a cancellation token and cancels it
    when the client disconnects.
    
    Usage:
        async with handle_client_disconnect(request) as cancellation_manager:
            # Pass cancellation_manager.is_cancelled as the cancellation_token
            # to database operations
            result = await execute_query_with_cancellation(
                sql, db_id, cancellation_token=cancellation_manager.is_cancelled
            )
    """
    cancellation_manager = CancellationManager()
    
    async with create_task_group() as tg:
        async def watch_disconnect():
            """Watch for client disconnection and cancel operations."""
            try:
                while True:
                    # Use a timeout to periodically check if we should exit
                    try:
                        message = await asyncio.wait_for(request.receive(), timeout=1.0)
                        if message["type"] == "http.disconnect":
                            client = f"{request.client.host}:{request.client.port}" if request.client else "-:-"
                            logger.info(f'{client} - "{request.method} {request.url.path}" disconnected')
                            cancellation_manager.cancel()
                            tg.cancel_scope.cancel()
                            break
                    except asyncio.TimeoutError:
                        # Check if we've been cancelled by the task group
                        if cancellation_manager.is_cancelled():
                            break
                        # Continue watching for disconnect
                        continue
            except Exception as e:
                logger.debug(f"Disconnect watcher error: {e}")
                cancellation_manager.cancel()
        
        # Start the disconnect watcher
        tg.start_soon(watch_disconnect)
        
        try:
            yield cancellation_manager
        finally:
            # Cancel any remaining tasks
            tg.cancel_scope.cancel()