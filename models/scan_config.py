from sqlalchemy import Column, String, ForeignKey
from .base import Base


class ScanConfig(Base):
    __tablename__ = "tbl_scan_config"

    scan_instance_id = Column(String, ForeignKey("tbl_scan_instance.guid"), nullable=False, primary_key=True)
    component = Column(String, nullable=False, primary_key=True)
    opt = Column(String, nullable=False, primary_key=True)
    val = Column(String, nullable=False)