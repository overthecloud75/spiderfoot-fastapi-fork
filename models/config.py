from sqlalchemy import Column, String
from .base import Base


class Config(Base):
    __tablename__ = "tbl_config"

    scope = Column(String, primary_key=True)
    opt = Column(String, primary_key=True)
    val = Column(String, nullable=False)