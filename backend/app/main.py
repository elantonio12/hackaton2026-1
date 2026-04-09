from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, containers, routes, reports, collectors, sensors, predictions, metrics, user
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

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(containers.router, prefix="/api/v1/containers", tags=["containers"])
app.include_router(routes.router, prefix="/api/v1/routes", tags=["routes"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(collectors.router, prefix="/api/v1/collectors", tags=["collectors"])
app.include_router(sensors.router, prefix="/api/v1/sensors", tags=["sensors"])
app.include_router(predictions.router, prefix="/api/v1/predictions", tags=["predictions"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(user.router, prefix="/api/v1/user", tags=["user"])


@app.on_event("startup")
async def startup():
    # Seed default admin user
    auth.seed_admin()

    # Seed sensor registry
    sensors.seed_sensor_registry()

    # Entrenar modelo de llenado de contenedores
    from app.services.prediction import generate_seed_history, train_initial_model
    from app.api.routes.sensors import sensor_registry
    generate_seed_history(sensor_registry)
    train_initial_model()

    # Entrenar modelo de llegada de camiones
    from app.services.truck_prediction import train_initial_model as train_truck_model
    train_truck_model()


@app.get("/health")
async def health_check():
    return {"status": "ok"}
