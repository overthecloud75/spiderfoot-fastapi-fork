async def should_run_middleware(request) -> bool:
    """미들웨어의 실행 여부를 결정
    """
    path = request.url.path
    method = request.method
    if path in ['/', '/login', '/register', '/docs', '/share', '/openapi.json']:
        return False
    return False