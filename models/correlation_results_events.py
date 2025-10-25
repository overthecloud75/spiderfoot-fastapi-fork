from sqlalchemy import Column, String, ForeignKey, Index
from sqlalchemy.orm import relationship
from .base import Base


class ScanCorrelationResultsEvents(Base):
    __tablename__ = "tbl_scan_correlation_results_events"

    correlation_id = Column(String, ForeignKey("tbl_scan_correlation_results.id"), nullable=False, primary_key=True)
    event_hash = Column(String, ForeignKey("tbl_scan_results.hash"), nullable=False, primary_key=True)

    __table_args__ = (
        Index("idx_scan_correlation_events", "correlation_id"),
    )