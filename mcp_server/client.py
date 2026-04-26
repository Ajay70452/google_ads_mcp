"""Async HTTP client wrapper for the FastAPI backend."""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 30.0


async def call_backend(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=TIMEOUT) as client:
        for attempt in range(3):
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                detail = e.response.json().get("detail", str(e))
                raise RuntimeError(f"Backend error {e.response.status_code}: {detail}")
            except httpx.TransportError as e:
                if attempt == 2:
                    raise RuntimeError(f"Backend unreachable after 3 attempts: {e}")


async def get(path: str, params: dict = None) -> dict:
    return await call_backend("GET", path, params=params)


async def post(path: str, body: dict) -> dict:
    return await call_backend("POST", path, json=body)
