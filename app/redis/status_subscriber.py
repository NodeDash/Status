#!/usr/bin/env python3
"""
Redis subscriber for device status events.
Listens for Redis keyspace events and updates device statuses in the database.
"""

import os
import sys
import time
import logging
import threading
import signal
from redis import Redis

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.redis.redis_manager import RedisDeviceManager
from app.db.database import SessionLocal
from app.models.device import DeviceStatus
from app.crud.device import update_device_status

logger = logging.getLogger(__name__)


class DeviceStatusSubscriber:
    """
    Subscriber for Redis keyspace events related to device status.
    Listens for expired keys and updates device status in the database.
    """

    def __init__(self, host="localhost", port=6379, db=0, password=None):
        """Initialize Redis pubsub connection."""
        self.redis = Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )
        self.pubsub = self.redis.pubsub()
        self.running = False
        self.thread = None
        self.device_mgr = RedisDeviceManager(host, port, db, password)
        logger.info(f"Device status subscriber initialized: {host}:{port}/db{db}")

    def start(self):
        """Start the subscriber in a separate thread."""
        self._subscribe_to_events()
        self.running = True
        self.thread = threading.Thread(target=self._listen_for_events)
        self.thread.daemon = True
        self.thread.start()
        logger.info("Device status subscriber started")

    def stop(self):
        """Stop the subscriber."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.pubsub.unsubscribe()
        self.pubsub.close()
        logger.info("Device status subscriber stopped")

    def _subscribe_to_events(self):
        """Subscribe to Redis keyspace events for key expiration."""
        # Subscribe to key expiration events in keyspace notifications
        self.pubsub.psubscribe("__keyevent@*__:expired")
        logger.info("Subscribed to Redis key expiration events")

    def _listen_for_events(self):
        """Listen for Redis keyspace events and process them."""
        try:
            for message in self.pubsub.listen():
                if not self.running:
                    break

                if message["type"] == "pmessage":
                    # Extract the expired key name
                    expired_key = message["data"]
                    self._process_expired_key(expired_key)

        except Exception as e:
            logger.error(f"Error in event listener: {e}")
            self.running = False

    def _process_expired_key(self, key):
        """Process an expired key event by updating device status."""
        device_id = RedisDeviceManager.get_device_id_from_key(key)
        if device_id is None:
            logger.debug(f"Ignoring non-device key: {key}")
            return

        logger.info(f"Device {device_id} key expired - marking offline")

        # Update device status in database
        db = SessionLocal()
        try:
            update_device_status(db, device_id=device_id, status=DeviceStatus.OFFLINE)
            db.commit()
            logger.info(f"Device {device_id} status updated to OFFLINE")
        except Exception as e:
            logger.error(f"Error updating device {device_id} status: {e}")
            db.rollback()
        finally:
            db.close()


def run_subscriber():
    """Run the subscriber as a daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    subscriber = DeviceStatusSubscriber()

    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        subscriber.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        subscriber.start()
        logger.info("Device status subscriber running. Press Ctrl+C to stop.")
        # Keep the main thread alive
        while subscriber.running:
            time.sleep(1)
    except Exception as e:
        logger.error(f"Error in subscriber: {e}")
    finally:
        subscriber.stop()


if __name__ == "__main__":
    run_subscriber()
