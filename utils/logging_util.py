import time

from configs import logger

def get_access_logging(start_time, request, response):
    client_ip = request.client.host if request.client else 'Unknown'
    process_time = time.time() - start_time
    log_msg = f'{client_ip} - {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s'
    logger.info(log_msg)