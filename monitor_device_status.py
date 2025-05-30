#!/usr/bin/env python3
"""
Device Status Monitor

This script shows the current status of all devices, including:
- Current status in the database
- TTL remaining in Redis (for online devices)
- Most recent history event for each device

Run this script to get a snapshot of your device status system.
"""

import sys
import time
from datetime import datetime
from sqlalchemy.orm import joinedload
from app.db.database import SessionLocal
from app.models.device import Device
from app.models.device_history import DeviceHistory
from app.redis.redis_manager import RedisDeviceManager
from app.core.config import settings


def format_time_remaining(ttl_seconds):
    """Format TTL seconds into a human-readable format"""
    if ttl_seconds is None:
        return "No TTL"

    if ttl_seconds <= 0:
        return "Expired"

    minutes, seconds = divmod(int(ttl_seconds), 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def get_device_status():
    """
    Get comprehensive device status information combining database and Redis data.

    Returns a list of dictionaries with device status information.
    """
    db = SessionLocal()
    # Initialize RedisDeviceManager instead of RedisClient
    redis_manager = RedisDeviceManager(
        host=getattr(settings, "REDIS_HOST", "localhost"),
        port=getattr(settings, "REDIS_PORT", 6379),
        db=getattr(settings, "REDIS_DB", 0),
        password=getattr(settings, "REDIS_PASSWORD", None),
    )
    status_info = []

    try:
        # Get all devices with their latest history entry
        devices = db.query(Device).all()

        for device in devices:
            device_id = device.id

            # Get device's latest history entry
            latest_history = (
                db.query(DeviceHistory)
                .filter(DeviceHistory.device_id == device_id)
                .order_by(DeviceHistory.timestamp.desc())
                .first()
            )

            # Get TTL from Redis for this device
            ttl = redis_manager.get_device_ttl(device_id)

            history_info = {}
            if latest_history:
                history_info = {
                    "timestamp": latest_history.timestamp,
                    "event": latest_history.event,
                    "data": latest_history.data,
                }

            # Check if Redis key exists
            redis_status = redis_manager.get_device_status(device_id)

            status_info.append(
                {
                    "id": device_id,
                    "name": device.name,
                    "status": device.status,
                    "expected_transmit_time": device.expected_transmit_time,
                    "ttl": ttl,
                    "ttl_formatted": format_time_remaining(ttl),
                    "redis_key_exists": redis_status == "online",
                    "latest_history": history_info,
                }
            )

        return status_info

    except Exception as e:
        print(f"Error fetching device status: {e}")
        return []
    finally:
        db.close()


def print_device_status():
    """
    Print a formatted display of all device statuses
    """
    status_info = get_device_status()

    if not status_info:
        print("No devices found in the database.")
        return

    print("\n" + "=" * 100)
    print(
        f"{'ID':^5} | {'NAME':^20} | {'STATUS':^10} | {'TTL REMAINING':^15} | {'LAST EVENT':^40}"
    )
    print("-" * 100)

    for device in status_info:
        # Format history information
        history_text = "No history"
        if device.get("latest_history"):
            history = device["latest_history"]
            timestamp = history["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            event = history["event"]
            data = history.get("data", {})
            status_change = ""
            if data and "msg" in data:
                status_change = data["msg"]
            history_text = f"{timestamp} - {event} - {status_change}"

        # Colorize status (ANSI colors)
        status_color = "\033[92m"  # Green for online
        if device["status"] == "offline":
            status_color = "\033[91m"  # Red for offline
        elif device["status"] == "maintenance":
            status_color = "\033[93m"  # Yellow for maintenance
        reset_color = "\033[0m"

        # Add an indicator if Redis and DB are out of sync
        sync_status = ""
        if device["status"] == "online" and not device["redis_key_exists"]:
            sync_status = (
                " ⚠️"  # Warning emoji if device is online in DB but not in Redis
            )
        elif device["status"] == "offline" and device["redis_key_exists"]:
            sync_status = (
                " ⚠️"  # Warning emoji if device is offline in DB but has Redis key
            )

        print(
            f"{device['id']:^5} | {device['name'][:20]:^20} | {status_color}{device['status']:^10}{reset_color}{sync_status} | {device['ttl_formatted']:^15} | {history_text[:40]:40}"
        )

    print("=" * 100)
    print(f"Total devices: {len(status_info)}")
    print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)


if __name__ == "__main__":
    try:
        print_device_status()
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
        sys.exit(0)
