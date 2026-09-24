"""FastAPI application: CORS, error handlers, routers under /api."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, dashboard, grns, invoices, masters, pos, prs, quotations
from app.core.config import settings
from app.core.errors import register_error_handlers

app = FastAPI(
    title="Purchase Management System",
    description="Procure-to-pay workflow: PR → approval → quotations → PO → GRN → invoice → payment.",
    version="0.4.0",
    swagger_ui_parameters={"persistAuthorization": True, "defaultModelsExpandDepth": 0},
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
