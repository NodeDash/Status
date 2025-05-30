#!/usr/bin/env python3
"""
Redis manager for device status service.
Handles Redis connections and operations related to device status tracking.
"""

import redis
import logging
from typing import Optional
from app.models.device import DeviceStatus

logger = logging.getLogger(__name__)


class RedisDeviceManager:
    """Manages device status using Redis TTL mechanism."""

    # Prefix for device status keys in Redis
    KEY_PREFIX = "device:status:"

    def __init__(self, host="localhost", port=6379, db=0, password=None):
        """Initialize Redis connection."""
        self.redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,  # Return strings instead of bytes
        )
        self._configure_keyspace_events()
        logger.info(f"Redis connection established to {host}:{port}/db{db}")

    def _configure_keyspace_events(self):
        """Configure Redis to emit keyspace events for key expiration."""
        try:
            self.redis.config_set("notify-keyspace-events", "Ex")
            logger.info("Redis keyspace events configured for expiration events")
        except redis.exceptions.ResponseError as e:
            logger.warning(f"Could not configure Redis keyspace events: {e}")
            logger.warning(
                "You may need to configure Redis manually to enable keyspace events"
            )

    def set_device_online(self, device_id: int, ttl_seconds: int) -> bool:
        """
        Mark a device as online by setting a Redis key with TTL.

        Args:
            device_id: Unique identifier for the device
            ttl_seconds: Time-to-live in seconds before the device is considered offline

        Returns:
            bool: Success status
        """
        key = f"{self.KEY_PREFIX}{device_id}"
        try:
            # Ensure TTL is at least 1 second
            ttl_seconds = max(1, ttl_seconds)
            self.redis.setex(key, ttl_seconds, DeviceStatus.ONLINE)
            logger.debug(f"Device {device_id} set online with TTL of {ttl_seconds}s")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error setting device {device_id} online: {e}")
            return False

    def get_device_status(self, device_id: int) -> Optional[str]:
        """
        Get current device status from Redis.

        Args:
            device_id: Unique identifier for the device

        Returns:
            str: "online" if device key exists, None otherwise
        """
        key = f"{self.KEY_PREFIX}{device_id}"
        try:
            if self.redis.exists(key):
                ttl = self.redis.ttl(key)
                logger.debug(f"Device {device_id} is online with {ttl}s remaining")
                return DeviceStatus.ONLINE
            else:
                logger.debug(f"Device {device_id} is offline (no Redis key)")
                return DeviceStatus.OFFLINE
        except redis.exceptions.RedisError as e:
            logger.error(f"Error getting status for device {device_id}: {e}")
            return None

    def get_device_ttl(self, device_id: int) -> Optional[int]:
        """
        Get remaining TTL for a device.

        Args:
            device_id: Unique identifier for the device

        Returns:
            int: Remaining TTL in seconds, or None if device is offline
        """
        key = f"{self.KEY_PREFIX}{device_id}"
        try:
            ttl = self.redis.ttl(key)
            return ttl if ttl > 0 else None
        except redis.exceptions.RedisError as e:
            logger.error(f"Error getting TTL for device {device_id}: {e}")
            return None

    def remove_device(self, device_id: int) -> bool:
        """
        Remove device status from Redis.

        Args:
            device_id: Unique identifier for the device

        Returns:
            bool: Success status
        """
        key = f"{self.KEY_PREFIX}{device_id}"
        try:
            self.redis.delete(key)
            logger.debug(f"Device {device_id} removed from Redis")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error removing device {device_id}: {e}")
            return False

    @classmethod
    def get_device_id_from_key(cls, key: str) -> Optional[int]:
        """
        Extract device ID from Redis key.

        Args:
            key: Redis key name including prefix

        Returns:
            int: Device ID or None if key format is invalid
        """
        if key and key.startswith(cls.KEY_PREFIX):
            try:
                return int(key[len(cls.KEY_PREFIX) :])
            except ValueError:
                return None
        return None
