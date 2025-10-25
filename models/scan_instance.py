from sqlalchemy import Column, String, Integer
from .base import Base


class ScanInstance(Base):
    __tablename__ = "tbl_scan_instance"

    guid = Column(String, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    seed_target = Column(String, nullable=False)
    created = Column(Integer, default=0)
    started = Column(Integer, default=0)
    ended = Column(Integer, default=0)
    status = Column(String, nullable=False)