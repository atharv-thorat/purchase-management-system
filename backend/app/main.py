"""FastAPI application: CORS, error handlers, routers under /api, offline API docs."""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import auth, dashboard, grns, invoices, masters, pos, prs, quotations
from app.core.config import settings
from app.core.errors import register_error_handlers

app = FastAPI(
    title="Purchase Management System",
    description="Procure-to-pay workflow: PR → approval → quotations → PO → GRN → invoice → payment.",
    version="0.4.0",
    swagger_ui_parameters={"persistAuthorization": True, "defaultModelsExpandDepth": 0},
    # Swagger UI is served from vendored files below instead of a CDN, so /docs works offline.
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

api = APIRouter(prefix="/api")


@api.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, dashboard, prs, quotations, pos, grns, invoices, masters):
    api.include_router(module.router)
app.include_router(api)

# ---- API docs, fully offline (Swagger UI 5 vendored in app/static/swagger-ui, Apache-2.0) ---------

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — API docs",
        oauth2_redirect_url="/docs/oauth2-redirect",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
        swagger_ui_parameters=app.swagger_ui_parameters,
    )


@app.get("/docs/oauth2-redirect", include_in_schema=False)
def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()
