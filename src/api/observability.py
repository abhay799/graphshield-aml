from __future__ import annotations
import json, logging, time, uuid
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('graphshield_http_requests_total','GraphShield HTTP requests',['method','path','status'])
REQUEST_LATENCY = Histogram('graphshield_http_request_duration_seconds','GraphShield HTTP request latency',['method','path'])

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'timestamp':self.formatTime(record),'level':record.levelname,'logger':record.name,'message':record.getMessage()})

def install_observability(app: FastAPI) -> None:
    logger = logging.getLogger('graphshield.api')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    @app.middleware('http')
    async def observe_request(request: Request, call_next):
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get('route')
            path = getattr(route, 'path', request.url.path)
            REQUEST_COUNT.labels(request.method,path,str(status)).inc()
            REQUEST_LATENCY.labels(request.method,path).observe(duration)
            logger.info('request method=%s path=%s status=%s duration_ms=%.2f request_id=%s',request.method,path,status,duration*1000,request_id)
        response.headers['X-Request-ID'] = request_id
        return response

    @app.get('/metrics', include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
