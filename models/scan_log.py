from sqlalchemy import Column, String, Integer, ForeignKey, Index, column
from sqlalchemy.orm import declarative_base, column_property
from .base import Base


class ScanLog(Base):
    __tablename__ = "tbl_scan_log"

    scan_instance_id = Column(String, ForeignKey("tbl_scan_instance.guid"), nullable=False, primary_key=True)
    generated = Column(Integer, nullable=False, primary_key=True)
    component = Column(String, nullable=True)
    type = Column(String, nullable=False)
    message = Column(String, nullable=True)

     # ✅ SQLite의 숨겨진 rowid를 ORM에서 접근 가능하도록 매핑
    rowid = column_property(column("rowid", Integer))

    __table_args__ = (
        Index("idx_scan_logs", "scan_instance_id"),
    )