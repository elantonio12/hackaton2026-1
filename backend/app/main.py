from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import containers, routes, reports
from app.core.config import settings

app = FastAPI(
    title="EcoRuta API",
    description="Sistema de Gestión de Residuos con Rutas Dinámicas - Hackaton Genius Area",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(containers.router, prefix="/api/v1/containers", tags=["containers"])
app.include_router(routes.router, prefix="/api/v1/routes", tags=["routes"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
