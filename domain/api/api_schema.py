from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# 스캔 목록의 각 항목을 위한 Pydantic 모델
class RiskMatrix(BaseModel):
    HIGH: int
    MEDIUM: int
    LOW: int
    INFO: int

class ScanStatus(BaseModel):
    name: str
    target: str
    created: str
    started: str
    ended: str
    status: str
    risk_matrix: RiskMatrix

class ScanRequest(BaseModel):
    id: str

class ScanErrorsRequest(BaseModel):
    id: str
    limit: int = 0

class ScanSummaryRequest(BaseModel):
    id: str
    by: str

class ScanError(BaseModel):
    generated: str
    module: str
    error_message: str

class ScanLogRequest(BaseModel):
    id: str  
    limit: int = 0  
    rowId: str = None  
    reverse: str = None 

class ScanEventResultsUniqueRequest(BaseModel):
    id: str
    eventType: str
    filterfp: bool = False

class ScanEventResutsRequest(BaseModel):
    id: str
    eventType: str = None
    filterfp: bool = False
    correlationId: str = None

class ScanElementTypeDiscoveryRequest(BaseModel):
    id: str
    eventType: str

class ResultSetFpRequest(BaseModel):
    id: str
    resultids: str
    fp: str

ScanErrorResponse = List[ScanError]

class ScanItem(BaseModel):
    id: str  # row[0]
    name: str  # row[1]
    target: str  # row[2]
    created: str  # row[3]
    started: str  # row[4]
    finished: str  # row[5]
    status: str  # row[6]
    progress: int  # row[7]
    risk_matrix: RiskMatrix

# 응답 리스트를 위한 모델
ScanListResponse = List[ScanItem]