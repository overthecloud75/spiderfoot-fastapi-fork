from sqlalchemy import Column, String, Integer
from .base import Base


class EventTypes(Base):
    __tablename__ = "tbl_event_types"

    event = Column(String, primary_key=True, nullable=False)
    event_descr = Column(String, nullable=False)
    event_raw = Column(Integer, nullable=False, default=0)
    event_type = Column(String, nullable=False)