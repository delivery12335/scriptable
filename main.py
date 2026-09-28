import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import router
from config import Settings, load_settings
from database import Database
from services.cache_service import CacheService, SourceUnavailable
from services.ceiti_client import CeitiClient, GroupNotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_path)
        await db.initialize()
        async with httpx.AsyncClient(timeout=settings.http_timeout, transport=transport,
                                     headers={"User-Agent": "CEITI-Notifications/1.0", "Cache-Control": "no-cache"}) as http:
            app.state.settings = settings
            app.state.cache = CacheService(db, CeitiClient(http), settings)
            await app.state.cache.refresh_all()
            task = asyncio.create_task(app.state.cache.run())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="CEITI Notifications", version="1.0.0", lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(SourceUnavailable)
    async def unavailable(request: Request, exc: SourceUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "60"})

    @app.exception_handler(GroupNotFound)
    async def unknown_group(request: Request, exc: GroupNotFound):
        return JSONResponse(status_code=404, content={"detail": f"Unknown CEITI group: {exc}"})

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        response = await call_next(request)
        log.info("%s %s status=%d", request.method, request.url.path, response.status_code)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
