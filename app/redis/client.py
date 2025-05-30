#!/usr/bin/env python3
"""
Simple Redis client for updating device status from any application.
This client can be used to update Redis key TTLs when device data is received.
"""

import redis
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Redis key prefix (must match the one used in the device status service)
DEVICE_STATUS_KEY_PREFIX = "device:status:"


class RedisClient:
    """Redis client for device status management."""

    def __init__(self, host="localhost", port=6379, db=0, password=None):
        """Initialize Redis connection."""
        self.redis = redis.Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )
        logger.info(f"Redis client initialized: {host}:{port}/db{db}")

    def set_device_online(self, device_id: int, ttl_seconds: int) -> bool:
        """
        Mark a device as online by setting a Redis key with TTL.

        Args:
            device_id: Unique identifier for the device
            ttl_seconds: Time-to-live in seconds before the device is considered offline

        Returns:
            bool: Success status
        """
        key = f"{DEVICE_STATUS_KEY_PREFIX}{device_id}"
        try:
            # Ensure TTL is at least 1 second
            ttl_seconds = max(1, ttl_seconds)
            self.redis.setex(key, ttl_seconds, "online")
            logger.debug(f"Device {device_id} set online with TTL of {ttl_seconds}s")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error setting device {device_id} online: {e}")
            return False
