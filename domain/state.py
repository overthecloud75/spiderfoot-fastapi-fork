from copy import deepcopy
import multiprocessing as mp

from sflib import SpiderFoot
from spiderfoot import SpiderFootDb
from spiderfoot.logger import logListenerSetup, logWorkerSetup
from configs import SF_CONFIG, logger


class AppState:
    """SpiderFootWebUi의 설정 및 데이터베이스 핸들러를 관리하는 클래스."""
    def __init__(self):
        self.defaultConfig: Dict[str, Any] = deepcopy(SF_CONFIG)
        self.dbh: Optional[SpiderFootDb] = SpiderFootDb(init=True)
        sf = SpiderFoot(self.defaultConfig)
        self.config: Dict[str, Any] = sf.configUnserialize(self.dbh.configGet(), self.defaultConfig)
        self.loggingQueue: mp.Queue = mp.Queue()
        
        logListenerSetup(self.loggingQueue, self.config)
        logWorkerSetup(self.loggingQueue)

state = AppState()
logger.info("Initialized AppState instance.")

# 라우터 함수에서 state에 접근하기 위한 의존성 주입
def get_dbh() -> SpiderFootDb:
    """데이터베이스 핸들러를 반환하는 종속성 함수."""
    yield state.dbh