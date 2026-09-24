"""FastAPI application: CORS, error handlers, routers under /api."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth
from app.core.config import settings
from app.core.errors import register_error_handlers

app = FastAPI(
    title="Purchase Management System",
    description="Procure-to-pay workflow: PR → approval → quotations → PO → GRN → invoice → payment.",
    version="0.2.0",
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


api.include_router(auth.router)
app.include_router(api)
