"""
Enhanced WebSocket Manager with Channel Support
Handles real-time bidirectional communication for dashboard, tasks, logs, and scrapers
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional, List
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from enum import Enum

logger = logging.getLogger(__name__)


class Channel(str, Enum):
    """WebSocket channels for different data streams"""
    DASHBOARD = "dashboard"
    TASKS = "tasks"
    LOGS = "logs"
    WORKERS = "workers"
    SCRAPERS = "scrapers"
    DATA_SOURCES = "data_sources"
    INDIAMART = "indiamart"
    HEALTH = "health"
    GENERAL = "general"


class WebSocketConnectionManager:
    """
    Manages WebSocket connections with channel-based subscriptions
    Supports multiple channels per connection and broadcasting to specific channels
    """
    
    def __init__(self):
        # Map of channel -> set of websockets
        self.channel_connections: Dict[str, Set[WebSocket]] = {}
        # Map of websocket -> set of subscribed channels
        self.connection_channels: Dict[WebSocket, Set[str]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        logger.info("WebSocket Connection Manager initialized")
    
    async def connect(self, websocket: WebSocket, channels: Optional[List[str]] = None):
        """
        Accept WebSocket connection and subscribe to channels
        
        Args:
            websocket: The WebSocket connection
            channels: List of channels to subscribe to (default: ["general"])
        """
        await websocket.accept()
        
        if channels is None:
            channels = [Channel.GENERAL]
        
        async with self._lock:
            # Initialize connection tracking
            if websocket not in self.connection_channels:
                self.connection_channels[websocket] = set()
            
            # Subscribe to channels
            for channel in channels:
                if channel not in self.channel_connections:
                    self.channel_connections[channel] = set()
                
                self.channel_connections[channel].add(websocket)
                self.connection_channels[websocket].add(channel)
        
        logger.info(f"WebSocket connected to channels: {channels}")
        
        # Send connection confirmation
        await self.send_to_connection(websocket, {
            "type": "connected",
            "channels": channels,
            "timestamp": datetime.now().isoformat()
        })
    
    async def disconnect(self, websocket: WebSocket):
        """
        Disconnect WebSocket and remove from all channels
        
        Args:
            websocket: The WebSocket connection to disconnect
        """
        async with self._lock:
            # Get channels this connection was subscribed to
            channels = self.connection_channels.get(websocket, set())
            
            # Remove from all channels
            for channel in channels:
                if channel in self.channel_connections:
                    self.channel_connections[channel].discard(websocket)
                    
                    # Clean up empty channel sets
                    if not self.channel_connections[channel]:
                        del self.channel_connections[channel]
            
            # Remove connection tracking
            if websocket in self.connection_channels:
                del self.connection_channels[websocket]
        
        logger.info(f"WebSocket disconnected from channels: {list(channels)}")
    
    async def subscribe(self, websocket: WebSocket, channel: str):
        """
        Subscribe an existing connection to a new channel
        
        Args:
            websocket: The WebSocket connection
            channel: Channel to subscribe to
        """
        async with self._lock:
            if channel not in self.channel_connections:
                self.channel_connections[channel] = set()
            
            self.channel_connections[channel].add(websocket)
            
            if websocket not in self.connection_channels:
                self.connection_channels[websocket] = set()
            
            self.connection_channels[websocket].add(channel)
        
        logger.info(f"WebSocket subscribed to channel: {channel}")
        
        # Send subscription confirmation
        await self.send_to_connection(websocket, {
            "type": "subscribed",
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
    
    async def unsubscribe(self, websocket: WebSocket, channel: str):
        """
        Unsubscribe a connection from a channel
        
        Args:
            websocket: The WebSocket connection
            channel: Channel to unsubscribe from
        """
        async with self._lock:
            if channel in self.channel_connections:
                self.channel_connections[channel].discard(websocket)
                
                if not self.channel_connections[channel]:
                    del self.channel_connections[channel]
            
            if websocket in self.connection_channels:
                self.connection_channels[websocket].discard(channel)
        
        logger.info(f"WebSocket unsubscribed from channel: {channel}")
        
        # Send unsubscription confirmation
        await self.send_to_connection(websocket, {
            "type": "unsubscribed",
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
    
    async def broadcast_to_channel(self, channel: str, message: Dict[str, Any]):
        """
        Broadcast message to all connections subscribed to a channel
        
        Args:
            channel: Channel to broadcast to
            message: Message data to send
        """
        async with self._lock:
            connections = self.channel_connections.get(channel, set()).copy()
        
        if not connections:
            return
        
        # Add channel and timestamp to message
        message_with_meta = {
            **message,
            "channel": channel,
            "timestamp": message.get("timestamp", datetime.now().isoformat())
        }
        
        message_json = json.dumps(message_with_meta)
        disconnected = set()
        
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected WebSockets
        if disconnected:
            for websocket in disconnected:
                await self.disconnect(websocket)
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """
        Broadcast message to all connected WebSockets
        
        Args:
            message: Message data to send
        """
        async with self._lock:
            all_connections = set(self.connection_channels.keys())
        
        if not all_connections:
            return
        
        message_with_meta = {
            **message,
            "timestamp": message.get("timestamp", datetime.now().isoformat())
        }
        
        message_json = json.dumps(message_with_meta)
        disconnected = set()
        
        for websocket in all_connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send broadcast message: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected WebSockets
        if disconnected:
            for websocket in disconnected:
                await self.disconnect(websocket)
    
    async def send_to_connection(self, websocket: WebSocket, message: Dict[str, Any]):
        """
        Send message to a specific WebSocket connection
        
        Args:
            websocket: The WebSocket connection
            message: Message data to send
        """
        try:
            message_with_meta = {
                **message,
                "timestamp": message.get("timestamp", datetime.now().isoformat())
            }
            await websocket.send_text(json.dumps(message_with_meta))
        except Exception as e:
            logger.error(f"Failed to send message to connection: {e}")
            await self.disconnect(websocket)
    
    def get_channel_count(self, channel: str) -> int:
        """Get number of connections subscribed to a channel"""
        return len(self.channel_connections.get(channel, set()))
    
    def get_total_connections(self) -> int:
        """Get total number of active connections"""
        return len(self.connection_channels)
    
    def get_connection_channels(self, websocket: WebSocket) -> Set[str]:
        """Get channels a connection is subscribed to"""
        return self.connection_channels.get(websocket, set()).copy()
    
    async def handle_message(self, websocket: WebSocket, message: str) -> Dict[str, Any]:
        """
        Handle incoming WebSocket message
        
        Args:
            websocket: The WebSocket connection
            message: Raw message string
            
        Returns:
            Response message dict
        """
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "ping":
                return {"type": "pong", "timestamp": datetime.now().isoformat()}
            
            elif message_type == "subscribe":
                channel = data.get("channel")
                if channel:
                    await self.subscribe(websocket, channel)
                    return {"type": "subscribed", "channel": channel}
                return {"type": "error", "message": "Channel not specified"}
            
            elif message_type == "unsubscribe":
                channel = data.get("channel")
                if channel:
                    await self.unsubscribe(websocket, channel)
                    return {"type": "unsubscribed", "channel": channel}
                return {"type": "error", "message": "Channel not specified"}
            
            elif message_type == "get_channels":
                channels = list(self.get_connection_channels(websocket))
                return {"type": "channels", "channels": channels}
            
            else:
                return {"type": "error", "message": f"Unknown message type: {message_type}"}
                
        except json.JSONDecodeError:
            return {"type": "error", "message": "Invalid JSON"}
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {"type": "error", "message": str(e)}


# Global WebSocket manager instance
ws_manager = WebSocketConnectionManager()
