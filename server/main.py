import asyncio
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import settings
from core.database import SessionLocal
from routers import api_agent, auth, servers, problems, terminal, files, users, audit, probes, maintenance, status_page
from routers import settings as settings_router
from services.problem_service import check_all_servers_stale, run_retention_prune
from services.probe_service import run_due_probes
from services.maintenance_service import evaluate_maintenance_windows


async def _stale_monitor_loop():
    """Periodically evaluate host connectivity, maintenance windows, and synthetic probes."""
    while True:
        await asyncio.sleep(15)
        db = SessionLocal()
        try:
            check_all_servers_stale(db)
            evaluate_maintenance_windows(db)
        except Exception:
            db.rollback()
        finally:
            db.close()
        try:
            await run_due_probes(SessionLocal)
        except Exception:
            pass


async def _retention_loop():
    """Periodically prune expired sessions and old telemetry/audit/command history."""
    while True:
        await asyncio.sleep(3600)
        db = SessionLocal()
        try:
            run_retention_prune(db)
        except Exception:
            db.rollback()
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_stale_monitor_loop())
    ret_task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        task.cancel()
        ret_task.cancel()


app = FastAPI(
    title="Pantau Server",
    version=settings.APP_VERSION,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


if settings.allowed_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

# Include Backend Routers
app.include_router(api_agent.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(servers.router)
app.include_router(files.router)
app.include_router(problems.router)
app.include_router(terminal.router)
app.include_router(audit.router)
app.include_router(settings_router.router)
app.include_router(probes.router)
app.include_router(maintenance.router)
app.include_router(status_page.router)

@app.get("/api/health")
def healthcheck():
    return {"status": "ok", "app": "pantau-server", "version": settings.APP_VERSION}

# Static Files & SPA fallback
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.SERVER_HOST, port=settings.SERVER_PORT, reload=True)
