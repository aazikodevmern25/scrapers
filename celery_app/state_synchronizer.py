"""
Advanced State Synchronization Module
Ensures consistent and reliable start/stop button functionality across all scraper instances
with immediate response to user input and proper state synchronization during operation.
"""

import asyncio
import threading
import time
import json
import logging
import os
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import weakref
import uuid
from contextlib import asynccontextmanager
import redis
from fastapi import WebSocket
import websockets

logger = logging.getLogger('state_synchronizer')

class ScraperState(Enum):
    """Scraper operational states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"

class ButtonState(Enum):
    """UI Button states"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    LOADING = "loading"

@dataclass
class ScraperStatus:
    """Comprehensive scraper status information"""
    scraper_id: str
    state: ScraperState
    start_time: Optional[datetime] = None
    last_update: datetime = field(default_factory=datetime.now)
    progress: float = 0.0
    items_processed: int = 0
    items_total: int = 0
    error_message: Optional[str] = None
    performance_stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'scraper_id': self.scraper_id,
            'state': self.state.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_update': self.last_update.isoformat(),
            'progress': self.progress,
            'items_processed': self.items_processed,
            'items_total': self.items_total,
            'error_message': self.error_message,
            'performance_stats': self.performance_stats
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScraperStatus':
        """Create from dictionary"""
        return cls(
            scraper_id=data['scraper_id'],
            state=ScraperState(data['state']),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']),
            progress=data.get('progress', 0.0),
            items_processed=data.get('items_processed', 0),
            items_total=data.get('items_total', 0),
            error_message=data.get('error_message'),
            performance_stats=data.get('performance_stats', {})
        )

@dataclass
class UIState:
    """UI component state information"""
    scraper_id: str
    start_button: ButtonState = ButtonState.ENABLED
    stop_button: ButtonState = ButtonState.DISABLED
    progress_visible: bool = False
    status_message: str = "Ready"
    last_update: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'scraper_id': self.scraper_id,
            'start_button': self.start_button.value,
            'stop_button': self.stop_button.value,
            'progress_visible': self.progress_visible,
            'status_message': self.status_message,
            'last_update': self.last_update.isoformat()
        }

class StateChangeEvent:
    """State change event for notifications"""
    
    def __init__(self, scraper_id: str, old_state: ScraperState, new_state: ScraperState, 
                 timestamp: Optional[datetime] = None):
        self.scraper_id = scraper_id
        self.old_state = old_state
        self.new_state = new_state
        self.timestamp = timestamp or datetime.now()
        self.event_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'event_id': self.event_id,
            'scraper_id': self.scraper_id,
            'old_state': self.old_state.value,
            'new_state': self.new_state.value,
            'timestamp': self.timestamp.isoformat()
        }

class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.connection_lock = threading.RLock()
    
    def add_connection(self, scraper_id: str, websocket: WebSocket):
        """Add WebSocket connection for a scraper"""
        with self.connection_lock:
            if scraper_id not in self.connections:
                self.connections[scraper_id] = set()
            self.connections[scraper_id].add(websocket)
    
    def remove_connection(self, scraper_id: str, websocket: WebSocket):
        """Remove WebSocket connection"""
        with self.connection_lock:
            if scraper_id in self.connections:
                self.connections[scraper_id].discard(websocket)
                if not self.connections[scraper_id]:
                    del self.connections[scraper_id]
    
    async def broadcast_to_scraper(self, scraper_id: str, message: Dict[str, Any]):
        """Broadcast message to all connections for a specific scraper"""
        with self.connection_lock:
            connections = self.connections.get(scraper_id, set()).copy()
        
        if not connections:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected WebSockets
        if disconnected:
            with self.connection_lock:
                if scraper_id in self.connections:
                    self.connections[scraper_id] -= disconnected
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all connections"""
        with self.connection_lock:
            all_connections = set()
            for connections in self.connections.values():
                all_connections.update(connections)
        
        if not all_connections:
            return
        
        message_json = json.dumps(message)
        
        for websocket in all_connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send broadcast message: {e}")

class StateSynchronizer:
    """Advanced state synchronization system"""
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize state synchronizer"""
        self.scrapers: Dict[str, ScraperStatus] = {}
        self.ui_states: Dict[str, UIState] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.websocket_manager = WebSocketManager()
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._background_tasks: List[asyncio.Task] = []
        
        # Redis connection (optional)
        self.redis_client = None
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info(f"Connected to Redis at {redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        
        # Start background tasks when event loop is available
        self._background_tasks_started = False
        
        logger.info("State synchronizer initialized")
    
    async def _start_background_tasks(self):
        """Start background cleanup and sync tasks"""
        if self._background_tasks_started:
            return
            
        self._background_tasks_started = True
        self._background_tasks.append(asyncio.create_task(self._cleanup_expired_states()))
        if self.redis_client:
            self._background_tasks.append(asyncio.create_task(self._sync_with_redis()))
        
        logger.info("Background tasks started")
    
    async def _cleanup_expired_states(self):
        """Clean up expired states periodically"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.now()
                expired_scrapers = []
                
                with self._lock:
                    for scraper_id, status in self.scrapers.items():
                        # Remove states older than 1 hour if scraper is stopped
                        if (status.state == ScraperState.STOPPED and 
                            current_time - status.last_update > timedelta(hours=1)):
                            expired_scrapers.append(scraper_id)
                    
                    for scraper_id in expired_scrapers:
                        del self.scrapers[scraper_id]
                        if scraper_id in self.ui_states:
                            del self.ui_states[scraper_id]
                
                if expired_scrapers:
                    logger.info(f"Cleaned up {len(expired_scrapers)} expired scraper states")
                
                await asyncio.sleep(300)  # Run every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def _sync_with_redis(self):
        """Synchronize state with Redis for distributed systems"""
        while not self._shutdown_event.is_set() and self.redis_client:
            try:
                # Publish current states to Redis
                with self._lock:
                    for scraper_id, status in self.scrapers.items():
                        key = f"scraper_state:{scraper_id}"
                        self.redis_client.setex(key, 300, json.dumps(status.to_dict()))
                
                await asyncio.sleep(10)  # Sync every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in Redis sync: {e}")
                await asyncio.sleep(30)
    
    def register_scraper(self, scraper_id: str, initial_state: ScraperState = ScraperState.STOPPED):
        """Register a new scraper"""
        with self._lock:
            if scraper_id not in self.scrapers:
                self.scrapers[scraper_id] = ScraperStatus(
                    scraper_id=scraper_id,
                    state=initial_state
                )
                self.ui_states[scraper_id] = UIState(scraper_id=scraper_id)
                logger.info(f"Registered scraper: {scraper_id}")
    
    def update_scraper_state(self, scraper_id: str, new_state: ScraperState, 
                           **kwargs) -> bool:
        """Update scraper state with validation and notifications"""
        with self._lock:
            if scraper_id not in self.scrapers:
                self.register_scraper(scraper_id)
            
            current_status = self.scrapers[scraper_id]
            old_state = current_status.state
            
            # Validate state transition
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(f"Invalid state transition for {scraper_id}: {old_state} -> {new_state}")
                return False
            
            # Update status
            current_status.state = new_state
            current_status.last_update = datetime.now()
            
            # Update additional fields
            for key, value in kwargs.items():
                if hasattr(current_status, key):
                    setattr(current_status, key, value)
            
            # Update UI state
            self._update_ui_state(scraper_id, new_state)
            
            # Create and handle event - safely handle async in sync context
            event = StateChangeEvent(scraper_id, old_state, new_state)
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(self._handle_state_change_event(event))
            except RuntimeError:
                # No event loop running - skip async event handling in sync context
                pass
            
            logger.info(f"State updated for {scraper_id}: {old_state} -> {new_state}")
            return True
    
    def _is_valid_transition(self, old_state: ScraperState, new_state: ScraperState) -> bool:
        """Validate state transitions"""
        valid_transitions = {
            ScraperState.STOPPED: [ScraperState.STARTING, ScraperState.ERROR],
            ScraperState.STARTING: [ScraperState.RUNNING, ScraperState.ERROR, ScraperState.STOPPED],
            ScraperState.RUNNING: [ScraperState.STOPPING, ScraperState.PAUSED, ScraperState.ERROR, ScraperState.COMPLETED],
            ScraperState.STOPPING: [ScraperState.STOPPED, ScraperState.ERROR],
            ScraperState.PAUSED: [ScraperState.RUNNING, ScraperState.STOPPING, ScraperState.ERROR],
            ScraperState.ERROR: [ScraperState.STOPPED, ScraperState.STARTING],
            ScraperState.COMPLETED: [ScraperState.STOPPED, ScraperState.STARTING]
        }
        
        return new_state in valid_transitions.get(old_state, [])
    
    def _update_ui_state(self, scraper_id: str, scraper_state: ScraperState):
        """Update UI state based on scraper state"""
        ui_state = self.ui_states[scraper_id]
        
        if scraper_state == ScraperState.STOPPED:
            ui_state.start_button = ButtonState.ENABLED
            ui_state.stop_button = ButtonState.DISABLED
            ui_state.progress_visible = False
            ui_state.status_message = "Ready"
            
        elif scraper_state == ScraperState.STARTING:
            ui_state.start_button = ButtonState.LOADING
            ui_state.stop_button = ButtonState.DISABLED
            ui_state.progress_visible = True
            ui_state.status_message = "Starting..."
            
        elif scraper_state == ScraperState.RUNNING:
            ui_state.start_button = ButtonState.DISABLED
            ui_state.stop_button = ButtonState.ENABLED
            ui_state.progress_visible = True
            ui_state.status_message = "Running"
            
        elif scraper_state == ScraperState.STOPPING:
            ui_state.start_button = ButtonState.DISABLED
            ui_state.stop_button = ButtonState.LOADING
            ui_state.progress_visible = True
            ui_state.status_message = "Stopping..."
            
        elif scraper_state == ScraperState.PAUSED:
            ui_state.start_button = ButtonState.ENABLED
            ui_state.stop_button = ButtonState.ENABLED
            ui_state.progress_visible = True
            ui_state.status_message = "Paused"
            
        elif scraper_state == ScraperState.ERROR:
            ui_state.start_button = ButtonState.ENABLED
            ui_state.stop_button = ButtonState.DISABLED
            ui_state.progress_visible = False
            ui_state.status_message = "Error"
            
        elif scraper_state == ScraperState.COMPLETED:
            ui_state.start_button = ButtonState.ENABLED
            ui_state.stop_button = ButtonState.DISABLED
            ui_state.progress_visible = False
            ui_state.status_message = "Completed"
        
        ui_state.last_update = datetime.now()
    
    async def _handle_state_change_event(self, event: StateChangeEvent):
        """Handle state change events"""
        try:
            # Call registered event handlers
            handlers = self.event_handlers.get(event.scraper_id, [])
            handlers.extend(self.event_handlers.get('*', []))  # Global handlers
            
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")
            
            # Broadcast to WebSocket connections
            await self._broadcast_state_update(event.scraper_id)
            
        except Exception as e:
            logger.error(f"Error handling state change event: {e}")
    
    async def _broadcast_state_update(self, scraper_id: str):
        """Broadcast state update to WebSocket connections"""
        try:
            with self._lock:
                scraper_status = self.scrapers.get(scraper_id)
                ui_state = self.ui_states.get(scraper_id)
            
            if scraper_status and ui_state:
                message = {
                    'type': 'state_update',
                    'scraper_id': scraper_id,
                    'scraper_status': scraper_status.to_dict(),
                    'ui_state': ui_state.to_dict(),
                    'timestamp': datetime.now().isoformat()
                }
                
                await self.websocket_manager.broadcast_to_scraper(scraper_id, message)
                
        except Exception as e:
            logger.error(f"Error broadcasting state update: {e}")
    
    def add_event_handler(self, scraper_id: str, handler: Callable):
        """Add event handler for state changes"""
        if scraper_id not in self.event_handlers:
            self.event_handlers[scraper_id] = []
        self.event_handlers[scraper_id].append(handler)
    
    def remove_event_handler(self, scraper_id: str, handler: Callable):
        """Remove event handler"""
        if scraper_id in self.event_handlers:
            try:
                self.event_handlers[scraper_id].remove(handler)
            except ValueError:
                pass
    
    def get_scraper_status(self, scraper_id: str) -> Optional[ScraperStatus]:
        """Get current scraper status"""
        with self._lock:
            return self.scrapers.get(scraper_id)
    
    def get_ui_state(self, scraper_id: str) -> Optional[UIState]:
        """Get current UI state"""
        with self._lock:
            return self.ui_states.get(scraper_id)
    
    def get_all_scrapers(self) -> Dict[str, ScraperStatus]:
        """Get all scraper statuses"""
        with self._lock:
            return self.scrapers.copy()
    
    def can_start_scraper(self, scraper_id: str) -> bool:
        """Check if scraper can be started"""
        with self._lock:
            status = self.scrapers.get(scraper_id)
            if not status:
                return True
            return status.state in [ScraperState.STOPPED, ScraperState.ERROR, ScraperState.COMPLETED]
    
    def can_stop_scraper(self, scraper_id: str) -> bool:
        """Check if scraper can be stopped"""
        with self._lock:
            status = self.scrapers.get(scraper_id)
            if not status:
                return False
            return status.state in [ScraperState.RUNNING, ScraperState.PAUSED]
    
    async def start_scraper(self, scraper_id: str) -> bool:
        """Initiate scraper start sequence"""
        if not self.can_start_scraper(scraper_id):
            return False
        
        return self.update_scraper_state(scraper_id, ScraperState.STARTING)
    
    async def stop_scraper(self, scraper_id: str) -> bool:
        """Initiate scraper stop sequence"""
        if not self.can_stop_scraper(scraper_id):
            return False
        
        return self.update_scraper_state(scraper_id, ScraperState.STOPPING)
    
    async def add_websocket_connection(self, scraper_id: str, websocket: WebSocket):
        """Add WebSocket connection for real-time updates"""
        self.websocket_manager.add_connection(scraper_id, websocket)
        
        # Send current state immediately
        await self._broadcast_state_update(scraper_id)
    
    async def remove_websocket_connection(self, scraper_id: str, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.websocket_manager.remove_connection(scraper_id, websocket)
    
    async def shutdown(self):
        """Shutdown the state synchronizer"""
        self._shutdown_event.set()
        
        for task in self._background_tasks:
            task.cancel()
        
        if self.redis_client:
            self.redis_client.close()
        
        logger.info("State synchronizer shutdown completed")

# Global state synchronizer instance
_global_synchronizer = None
_synchronizer_lock = threading.Lock()

def get_global_synchronizer() -> StateSynchronizer:
    """Get the global state synchronizer instance"""
    global _global_synchronizer
    if _global_synchronizer is None:
        redis_url = os.getenv('REDIS_URL')
        _global_synchronizer = StateSynchronizer(redis_url)
    return _global_synchronizer

def reset_global_synchronizer():
    """Reset global synchronizer (useful for testing)"""
    global _global_synchronizer
    
    with _synchronizer_lock:
        if _global_synchronizer:
            asyncio.create_task(_global_synchronizer.shutdown())
        _global_synchronizer = None

# Decorator for automatic state management
def with_state_sync(scraper_id: str):
    """Decorator to automatically manage scraper state"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            synchronizer = get_global_synchronizer()
            synchronizer.register_scraper(scraper_id)
            
            try:
                synchronizer.update_scraper_state(scraper_id, ScraperState.STARTING)
                synchronizer.update_scraper_state(scraper_id, ScraperState.RUNNING)
                
                result = await func(*args, **kwargs)
                
                synchronizer.update_scraper_state(scraper_id, ScraperState.COMPLETED)
                return result
                
            except Exception as e:
                synchronizer.update_scraper_state(scraper_id, ScraperState.ERROR, error_message=str(e))
                raise
        
        def sync_wrapper(*args, **kwargs):
            synchronizer = get_global_synchronizer()
            synchronizer.register_scraper(scraper_id)
            
            try:
                synchronizer.update_scraper_state(scraper_id, ScraperState.STARTING)
                synchronizer.update_scraper_state(scraper_id, ScraperState.RUNNING)
                
                result = func(*args, **kwargs)
                
                synchronizer.update_scraper_state(scraper_id, ScraperState.COMPLETED)
                return result
                
            except Exception as e:
                synchronizer.update_scraper_state(scraper_id, ScraperState.ERROR, error_message=str(e))
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

# Create global instance for easy import
state_synchronizer = get_global_synchronizer()