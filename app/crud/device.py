from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.models.device import Device, DeviceStatus
from app.models.device_history import DeviceHistory
from app.redis.client import RedisClient


def get_device(db: Session, device_id: int) -> Optional[Device]:
    """Get a device by ID"""
    query = db.query(Device).filter(Device.id == device_id)
    device = query.first()
    if not device:
        return None
    return device


def update_device_status(db: Session, device_id: int, status: str) -> bool:
    """
    Update only the status field of a device, avoiding any issues with other fields.
    Also updates Redis TTL if the device status is changed to ONLINE.

    Args:
        db: The database session
        device_id: The ID of the device to update
        status: The new status value

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Fetch the current status of the device
        db_device = get_device(db, device_id)
        if not db_device:
            return False

        current_status = db_device.status
        new_status = status

        # update the device status
        db_device.status = new_status
        db.add(db_device)
        db.commit()

        # If the device is now online, update Redis TTL
        if new_status == DeviceStatus.ONLINE and db_device.expected_transmit_time:
            try:
                redis_client = RedisClient.get_instance()
                ttl_seconds = db_device.expected_transmit_time * 60
                redis_client.set_device_online(int(device_id), int(ttl_seconds))
            except Exception as redis_error:
                # Log the error but don't fail the status update
                print(f"Error updating Redis for device {device_id}: {redis_error}")

        # create a history entry for the status change
        latest_history = (
            db.query(DeviceHistory)
            .filter(DeviceHistory.device_id == device_id)
            .order_by(DeviceHistory.timestamp.desc())
            .first()
        )

        timestamp = datetime.utcnow()
        if latest_history:
            timestamp = latest_history.timestamp

        # convert time to a string
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        db_history = DeviceHistory(
            device_id=device_id,
            event="status_change",
            data={
                "status": new_status,
                "previous_status": current_status,
                "msg": "Device status changed to " + new_status,
                "last_transmission": timestamp_str,
            },
            timestamp=datetime.utcnow(),
        )
        db.add(db_history)
        db.commit()
        db.refresh(db_history)

        return True
    except Exception as e:
        # Log the error
        print(f"Error updating device status: {e}")
        return False
