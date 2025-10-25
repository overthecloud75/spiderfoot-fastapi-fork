from sqlalchemy import Column, String, Integer, ForeignKey, Index
from .base import Base


class ScanResults(Base):
    __tablename__ = "tbl_scan_results"

    scan_instance_id = Column(String, ForeignKey("tbl_scan_instance.guid"), nullable=False, primary_key=True)
    hash = Column(String, nullable=False, primary_key=True)
    type = Column(String, ForeignKey("tbl_event_types.event"), nullable=False)
    generated = Column(Integer, nullable=False)
    confidence = Column(Integer, nullable=False, default=100)
    visibility = Column(Integer, nullable=False, default=100)
    risk = Column(Integer, nullable=False, default=0)
    module = Column(String, nullable=False)
    data = Column(String, nullable=True)
    false_positive = Column(Integer, nullable=False, default=0)
    source_event_hash = Column(String, nullable=True, default="ROOT")

    __table_args__ = (
        Index("idx_scan_results_id", "scan_instance_id"),
        Index("idx_scan_results_type", "scan_instance_id", "type"),
        Index("idx_scan_results_hash", "scan_instance_id", "hash"),
        Index("idx_scan_results_module", "scan_instance_id", "module"),
        Index("idx_scan_results_srchash", "scan_instance_id", "source_event_hash"),
    )
