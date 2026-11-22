import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import settings
from routers import api_agent, auth, servers, problems, terminal, files

app = FastAPI(
    title="Pantau Server",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Backend Routers
app.include_router(api_agent.router)
app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(files.router)
app.include_router(problems.router)
app.include_router(terminal.router)

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
