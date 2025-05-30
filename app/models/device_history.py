from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from datetime import datetime
from app.db.database import Base


class DeviceHistory(Base):
    __tablename__ = "device_history"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    event = Column(String, nullable=False)
    data = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
