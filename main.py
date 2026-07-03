import time
from collections import deque
from typing import Dict, Any, List
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI()

# --- STATE & STORAGE ---
START_TIME = time.time()
# In-memory ring buffer for the last 1000 logs to support the tail endpoint
LOG_BUFFER = deque(maxlen=1000)

# Live Prometheus Counter tracking requests by endpoint path
# Initialized with known paths to ensure they display as 0 initially
REQUEST_COUNTER: Dict[str, int] = {
    "/work": 0,
    "/metrics": 0,
    "/healthz": 0,
    "/logs/tail": 0
}

# --- RESPONSES ---
class WorkResponse(BaseModel):
    email: str = "your-email@example.com"  # Replace with your actual email if required
    done: int

class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_s: float = Field(..., ge=0.0)

# --- MIDDLEWARE FOR COUNTERS & LOGS ---
@app.middleware("http")
async def instrument_and_log(request: Request, call_next):
    path = request.url.path
    
    # Increment the live counter for the path
    if path in REQUEST_COUNTER:
        REQUEST_COUNTER[path] += 1
    else:
        REQUEST_COUNTER[path] = 1

    # Track start time for duration if needed, and execute request
    response = await call_next(request)
    
    # Generate a lightweight unique request ID (using timestamp + path hash for simplicity)
    request_id = f"req-{int(time.time() * 1000)}-{abs(hash(path)) % 10000}"
    
    # Structure the JSON log entry
    log_entry = {
        "level": "INFO",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "path": path,
        "request_id": request_id,
        "status_code": response.status_code
    }
    
    # Append to our live-tail buffer
    LOG_BUFFER.append(log_entry)
    
    # Also print to standard stdout for traditional log capture systems
    import json
    print(json.dumps(log_entry))
    
    return response

# --- ENDPOINTS ---

@app.get("/work", response_model=WorkResponse)
async def do_work(n: int = 1):
    # Simulate doing K units of work
    total = 0
    for i in range(n):
        total += i
    return WorkResponse(done=n)

@app.get("/metrics", response_class=Response)
async def get_metrics():
    # Construct standard Prometheus text format manually to avoid library overhead
    # and guarantee the counter dynamically responds to traffic instantly.
    lines = [
        "# HELP http_requests_total Total number of HTTP requests.",
        "# TYPE http_requests_total counter"
    ]
    for path, count in REQUEST_COUNTER.items():
        lines.append(f'http_requests_total{{path="{path}"}} {count}')
    
    # Prometheus requires a trailing newline
    metrics_text = "\n".join(lines) + "\n"
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4")

@app.get("/healthz", response_model=HealthResponse)
async def get_health():
    uptime = max(0.0, time.time() - START_TIME)
    return HealthResponse(uptime_s=uptime)

@app.get("/logs/tail", response_model=List[Dict[str, Any]])
async def tail_logs(limit: int = 10):
    # Ensure limit is positive and bounded
    limit = max(1, limit)
    
    # Get the last N elements from the ring buffer
    logs = list(LOG_BUFFER)[-limit:]
    
    # Return reversed order if you want the newest first, 
    # or keep as-is for standard chronological appending.
    return JSONResponse(content=logs)
