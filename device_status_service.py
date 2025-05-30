#!/usr/bin/env python3
"""
Device status service that uses Redis TTL for event-driven status tracking.
This service will:
1. Initialize devices in Redis based on database state
2. Update device statuses when transmissions are received
3. Listen for key expiry events to detect offline devices
"""

import logging

from app.db.database import SessionLocal
from app.models.device import Device, DeviceStatus
from app.models.device_history import DeviceHistory
from app.crud.device import update_device_status
from app.redis.redis_manager import RedisDeviceManager
from app.redis.status_subscriber import DeviceStatusSubscriber
from app.core.config import settings

from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("device_status_service")


class DeviceStatusService:
    """
    Service to manage device online/offline status using Redis TTL mechanism.
    """

    def __init__(
        self, redis_host=None, redis_port=None, redis_db=0, redis_password=None
    ):
        """Initialize the service with Redis and database connections."""
        # Use settings if available, otherwise use provided values or defaults
        self.redis_host = redis_host or getattr(settings, "REDIS_HOST", "localhost")
        self.redis_port = redis_port or getattr(settings, "REDIS_PORT", 6379)
        self.redis_db = redis_db or getattr(settings, "REDIS_DB", 0)
        self.redis_password = redis_password or getattr(
            settings, "REDIS_PASSWORD", None
        )

        self.redis_mgr = RedisDeviceManager(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
        )
        self.subscriber = DeviceStatusSubscriber(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
        )
        logger.info("Device Status Service initialized")

    def initialize_devices(self):
        """
        Initialize Redis with all devices from the database.
        Sets online status keys for all devices with expected transmit times.
        """
        db = SessionLocal()
        try:
            logger.info("Initializing device statuses in Redis")

            # Get all devices with expected transmission times
            devices = (
                db.query(Device).filter(Device.expected_transmit_time.isnot(None)).all()
            )

            if not devices:
                logger.info(
                    "No devices found with expected transmission time configured"
                )
                return

            logger.info(
                f"Found {len(devices)} devices with expected transmission time configured"
            )

            # Initialize each device in Redis
            for device in devices:
                # first check if the device is offline, if it is we dont want to set it online
                if device.status == DeviceStatus.OFFLINE:
                    logger.debug(
                        f"Device {device.id} ({device.name}) is OFFLINE, skipping initialization"
                    )
                    continue
                # Calculate TTL in seconds
                ttl_seconds = device.expected_transmit_time * 60

                # we have a ttl_seconds, we need to check the device history and find the last time it was online, marking the ttl_seconds to how longs left until its next expected transmit time
                device_history = (
                    db.query(DeviceHistory)
                    .filter(DeviceHistory.device_id == device.id)
                    .order_by(DeviceHistory.timestamp.desc())
                    .first()
                )
                if device_history:
                    last_online_time = device_history.timestamp
                    # we need to update the ttl to be last online time + expected transmit time
                    # if the last online time is in the future, we need to set the ttl to be the expected transmit time
                    if last_online_time > datetime.now():
                        # we need to set the ttl to be the expected transmit time
                        ttl_seconds = device.expected_transmit_time * 60
                    else:

                        ttl_seconds = (
                            datetime.now() - last_online_time
                        ).total_seconds() + (device.expected_transmit_time * 60)

                    # round to 0 decimal places
                    ttl_seconds = round(ttl_seconds, 0)
                    print(
                        f"Device {device.id} ({device.name}) last online at {last_online_time}, setting TTL to {ttl_seconds}s"
                    )
                else:
                    logger.warning(
                        f"No history found for device {device.id} ({device.name}), not setting TTL"
                    )
                    continue

                # Set the device as online in Redis
                self.redis_mgr.set_device_online(int(device.id), int(ttl_seconds))
                logger.info(
                    f"Device {device.id} ({device.name}) initialized with TTL of {ttl_seconds}s"
                )

            logger.info("Device initialization complete")

        except Exception as e:
            logger.error(f"Error initializing devices: {e}")
            # Re-raise for debugging if needed
            raise
        finally:
            db.close()

    def handle_device_transmission(self, device_id, timestamp=None):
        """
        Handle a new transmission from a device.
        Updates the device's online status in Redis and database.

        Args:
            device_id: The ID of the device that transmitted
            timestamp: Optional timestamp of the transmission
        """
        db = SessionLocal()
        try:
            # Get the device from the database
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                logger.warning(f"Device {device_id} not found in database")
                return False

            if not device.expected_transmit_time:
                logger.warning(
                    f"Device {device_id} has no expected transmit time configured"
                )
                return False

            # Calculate TTL in seconds
            ttl_seconds = device.expected_transmit_time * 60

            # Set the device as online in Redis
            self.redis_mgr.set_device_online(int(device_id), int(ttl_seconds))

            # Update device status in database if it's not already online
            if device.status != DeviceStatus.ONLINE:
                update_device_status(
                    db, device_id=device_id, status=DeviceStatus.ONLINE
                )
                db.commit()
                logger.info(
                    f"Device {device_id} ({device.name}) marked ONLINE after transmission"
                )
            else:
                logger.debug(
                    f"Device {device_id} ({device.name}) already ONLINE, TTL reset"
                )

            return True

        except Exception as e:
            logger.error(f"Error handling transmission from device {device_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def start_subscriber(self):
        """Start the Redis key expiry event subscriber."""
        self.subscriber.start()
        logger.info("Device status subscriber started")

    def stop_subscriber(self):
        """Stop the Redis key expiry event subscriber."""
        self.subscriber.stop()
        logger.info("Device status subscriber stopped")

    def run_service(self):
        """Run the complete device status service."""
        try:
            # Initialize devices from database into Redis
            self.initialize_devices()

            # Start the subscriber for expiry events
            self.start_subscriber()

            logger.info("Device Status Service running")
            return True

        except Exception as e:
            logger.error(f"Error starting Device Status Service: {e}")
            self.stop_subscriber()
            return False


# Singleton instance for use in FastAPI application
device_status_service = None


def get_device_status_service():
    """Get or create a singleton instance of the DeviceStatusService."""
    global device_status_service
    if device_status_service is None:
        device_status_service = DeviceStatusService()
    return device_status_service


if __name__ == "__main__":
    service = DeviceStatusService()
    service.run_service()

    # Keep the service running
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Service shutdown requested")
        service.stop_subscriber()
        logger.info("Service stopped")
