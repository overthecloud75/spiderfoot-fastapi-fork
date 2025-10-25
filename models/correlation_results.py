from sqlalchemy import Column, String, ForeignKey, Index
from .base import Base


class ScanCorrelationResults(Base):
    __tablename__ = "tbl_scan_correlation_results"

    id = Column(String, primary_key=True, nullable=False)
    scan_instance_id = Column(String, ForeignKey("tbl_scan_instance.guid"), nullable=False)
    title = Column(String, nullable=False)
    rule_risk = Column(String, nullable=False)
    rule_id = Column(String, nullable=False)
    rule_name = Column(String, nullable=False)
    rule_descr = Column(String, nullable=False)
    rule_logic = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_scan_correlation", "scan_instance_id", "id"),
    )