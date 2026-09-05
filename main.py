"""Root main.py entrypoint — runs RECLAIM FastAPI application via uvicorn."""

import uvicorn
from reclaim.main import app

if __name__ == "__main__":
    uvicorn.run("reclaim.main:app", host="0.0.0.0", port=8000, reload=False)
