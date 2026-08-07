"""InsightPilot AI - FastAPI app factory.

The app factory mounts the REST API from ``backend/api/routes.py`` and serves
the built React frontend (SPA fallback) in production. All data computation
happens in Pandas; the LLM (optional, provider-agnostic) is only used for
planning and phrasing insights.

Endpoints:
  GET    /api/health
  GET    /api/datasets
  POST   /api/datasets/upload      (multipart file upload)
  GET    /api/datasets/{id}
  POST   /api/analyze              (ask a natural-language question)
  GET    /api/history
  GET    /api/conversation
  DELETE /api/history/{id}
  GET    /api/suggestions/{id}
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.api.routes import router

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="InsightPilot AI",
        description="An autonomous AI Business Intelligence Agent over CSV/Excel datasets.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the built React frontend with an SPA fallback to index.html."""
        if full_path.startswith("api/"):
            raise _http404("Not found")
        if not FRONTEND_DIST.exists():
            return JSONResponse(
                {"detail": "Frontend not built. Run `npm run build` in frontend/ "
                           "or use the Vite dev server."},
                status_code=404,
            )
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

    return app


def _http404(detail: str):
    from fastapi import HTTPException

    return HTTPException(status_code=404, detail=detail)


app = create_app()
