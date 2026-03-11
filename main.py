#!/usr/bin/env python3
import httpx, time, os, json, logging, itertools
import threading
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.getenv("LOG_FILE", "router.log"))
    ]
)
logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
RPM_LIMIT       = int(os.getenv("RPM_LIMIT", 14))
RPD_LIMIT       = int(os.getenv("RPD_LIMIT", 490))
TIMEOUT         = int(os.getenv("REQUEST_TIMEOUT", 120))
KEYS_FILE       = Path(os.getenv("KEYS_FILE", "keys.json"))

class KeyStore:
    def __init__(self):
        self._keys: list[str] = []
        self._state: dict     = {}
        self._cycle           = iter([])
        self._mtime: float    = 0
        self._lock            = threading.Lock()
        self.reload()

    def reload(self) -> bool:
        try:
            mtime = KEYS_FILE.stat().st_mtime
        except FileNotFoundError:
            logger.error(f"Keys file not found: {KEYS_FILE}")
            return False

        if mtime == self._mtime:
            return False  # unchanged, skip
            
        # Optional tiny sleep to allow atomic file writes to complete
        time.sleep(0.05)
        
        try:
            data     = json.loads(KEYS_FILE.read_text())
            new_keys = [k.strip() for k in data.get("keys", []) if k.strip()]
        except Exception as e:
            logger.error(f"Failed to parse {KEYS_FILE}: {e}")
            return False

        if not new_keys:
            logger.error("keys.json has no valid keys")
            return False

        # Preserve state for keys that already exist
        new_state = {
            key: self._state.get(key, {
                "rpm": 0, "rpd": 0,
                "reset": time.time() + 60,
                "exhausted_until": 0,
                "total_requests": 0,
                "total_errors": 0,
                "last_used": None,
            })
            for key in new_keys
        }

        with self._lock:
            self._keys  = new_keys
            self._state = new_state
            self._cycle = itertools.cycle(new_keys)
            self._mtime = mtime
            logger.info(f"Keys reloaded: {len(new_keys)} active")
            
        return True

    def get_key(self) -> str | None:
        now = time.time()
        with self._lock:
            if not self._keys:
                return None
            for _ in range(len(self._keys)):
                key = next(self._cycle)
                s   = self._state[key]
                if now < s["exhausted_until"]:
                    continue
                if now > s["reset"]:
                    s["rpm"] = 0
                    s["reset"] = now + 60
                if s["rpm"] < RPM_LIMIT and s["rpd"] < RPD_LIMIT:
                    s["rpm"] += 1
                    s["rpd"] += 1
                    s["total_requests"] += 1
                    s["last_used"] = datetime.utcnow().isoformat()
                    return key
            return None

    def mark_exhausted(self, key: str):
        with self._lock:
            if key in self._state:
                self._state[key]["exhausted_until"] = time.time() + 60
                self._state[key]["total_errors"]    += 1
                logger.warning(f"Key exhausted: ...{key[-8:]}")

    def health(self) -> dict:
        now = time.time()
        with self._lock:
            return {
                f"...{key[-8:]}": {
                    "rpm": s["rpm"], "rpm_limit": RPM_LIMIT,
                    "rpd": s["rpd"], "rpd_limit": RPD_LIMIT,
                    "exhausted":      now < s["exhausted_until"],
                    "total_requests": s["total_requests"],
                    "total_errors":   s["total_errors"],
                    "last_used":      s["last_used"],
                }
                for key, s in self._state.items()
            }

    def reset_rpd(self):
        with self._lock:
            for s in self._state.values():
                s["rpd"] = 0

class KeysFileHandler(FileSystemEventHandler):
    def __init__(self, store: KeyStore):
        self.store = store
        
    def on_modified(self, event):
        if Path(event.src_path).absolute() == KEYS_FILE.absolute():
            logger.info("keys.json changed — reloading")
            self.store.reload()
            
    def on_created(self, event):
        if Path(event.src_path).absolute() == KEYS_FILE.absolute():
            logger.info("keys.json created/replaced — reloading")
            self.store.reload()

store = KeyStore()

try:
    if not KEYS_FILE.exists():
        KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEYS_FILE.write_text('{"keys":[]}')
except Exception as e:
    pass

event_handler = KeysFileHandler(store)
observer = Observer()
# Watch the directory where the keys file resides
observer.schedule(event_handler, path=str(KEYS_FILE.parent.absolute()), recursive=False)
observer.start()

app = FastAPI(title="Gemini Router")

@app.on_event("shutdown")
def shutdown_event():
    observer.stop()
    observer.join()

@app.post("/v1/{path:path}")
async def proxy(path: str, request: Request):
    body_bytes = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "authorization",
                              "x-goog-api-key", "connection")
    }
    headers["content-type"] = "application/json"

    is_streaming = False
    try:
        is_streaming = json.loads(body_bytes).get("stream", False)
    except Exception:
        pass

    key = store.get_key()
    if not key:
        return JSONResponse({"error": "All keys exhausted. Try again shortly."}, status_code=429)
    headers["Authorization"] = f"Bearer {key}"
    target = f"{GEMINI_BASE_URL}/{path}"
    logger.info(f"→ ...{key[-8:]} | {path}")

    try:
        if is_streaming:
            return await stream_response(target, headers, body_bytes, key)

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(target, headers=headers, content=body_bytes)

        if r.status_code == 429:
            store.mark_exhausted(key)
            key2 = store.get_key()
            if not key2:
                return JSONResponse({"error": "All keys exhausted"}, status_code=429)
            headers["Authorization"] = f"Bearer {key2}"
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(target, headers=headers, content=body_bytes)

        logger.info(f"✓ ...{key[-8:]} | {r.status_code}")
        return JSONResponse(content=r.json(), status_code=r.status_code)

    except httpx.TimeoutException:
        store.mark_exhausted(key)
        return JSONResponse({"error": "Request timed out"}, status_code=504)
    except Exception as e:
        logger.error(f"Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def stream_response(url: str, headers: dict, body: bytes, key: str):
    async def gen():
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", url, headers=headers, content=body) as r:
                if r.status_code == 429:
                    store.mark_exhausted(key)
                async for chunk in r.aiter_bytes():
                    yield chunk
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return store.health()

@app.get("/reset-rpd")
async def reset_rpd():
    store.reset_rpd()
    return {"status": "ok", "reset_at": datetime.utcnow().isoformat()}

@app.post("/reload")
async def force_reload():
    reloaded = store.reload()
    return {"reloaded": reloaded, "active_keys": len(store._keys)}
