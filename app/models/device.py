from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
)
from datetime import datetime
from app.db.database import Base
import enum


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    dev_eui = Column(
        String(16), nullable=True, unique=True, index=True
    )  # Made nullable for testing
    app_eui = Column(String(16), nullable=True)  # Made nullable for testing
    app_key = Column(String(32), nullable=True)  # Made nullable for testing
    status = Column(String, default=DeviceStatus.OFFLINE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Expected transmit time in minutes (from 1 minute to 24 hours)
    expected_transmit_time = Column(Integer, nullable=True)
