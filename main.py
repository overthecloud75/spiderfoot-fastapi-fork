import os
import sys
import time
import random
import signal
import multiprocessing as mp

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from domain.main import main_router
from domain.api import api_router
from utils import get_access_logging, should_run_middleware
from configs import SF_CONFIG, logger


# --- main function
def start_web_server() -> None:
    app = FastAPI()
    app.include_router(main_router.router)
    app.include_router(api_router.router)

    # Static files: SpiderFoot static directory 
    static_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if os.path.isdir(static_root):
        app.mount("/static", StaticFiles(directory=static_root), name="static")
    else:
        log.warning(f"Static directory not found: {static_root}")

    # 미들웨어를 사용하여 요청/응답 로깅
    @app.middleware('http')
    async def log_requests(request: Request, call_next):

        start_time = time.time()

        if not await should_run_middleware(request):
            try :
                response = await call_next(request)
                get_access_logging(start_time, request, response)
            except Exception as e:
                logger.error(e, exc_info=True)
                response = JSONResponse(
                    status_code=500,
                    content={'message': 'Internal Server Error'}
                )
                get_access_logging(start_time, request, response)
            return response

            try:
                response = await call_next(request)
            except Exception as e:
                logger.error(e, exc_info=True)
                response = JSONResponse(
                    status_code=500,
                    content={'message': 'Internal Server Error'}
                )
        get_access_logging(start_time, request, response)
        return response

    # 출력 메시지
    print("")
    print("*************************************************************")
    print(" Use SpiderFoot by starting your web browser")
    print("*************************************************************")
    print("")

    # 시그널 핸들러 (간단히)
    def handle_abort(signalnum, frame):
        logger.info("Abort signal received; exiting.")
        sys.exit(-1)

    signal.signal(signal.SIGINT, handle_abort)
    signal.signal(signal.SIGTERM, handle_abort)

    # Uvicorn 실행 (스레드에서)
    def run_uvicorn():
        uvicorn_cfg = {
            "app": app,
            "host": "0.0.0.0",
            "log_level": "info",
            "reload": False,
            "access_log": False 
        }

        # Uvicorn을 파이썬 API로 실행하면 로그/제어가 쉬움
        uvicorn.run(**uvicorn_cfg)
    run_uvicorn()

def main() -> None:
    logger.info('main start')
    start_web_server()

if __name__ == '__main__':
    mp.set_start_method("spawn", force=True)
    app = main()
