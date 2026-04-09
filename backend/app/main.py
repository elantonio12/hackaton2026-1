from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, containers, routes, reports, collectors, sensors, predictions, metrics, user, trucks
from app.core.config import settings

app = FastAPI(
    title="EcoRuta API",
    description="Sistema de Gestion de Residuos con Rutas Dinamicas - Hackaton Genius Area",
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
app.include_router(trucks.router, prefix="/api/v1/trucks", tags=["trucks"])


@app.on_event("startup")
async def startup():
    from sqlalchemy import select

    from app.db.database import async_session, run_migrations
    from app.db.models import Sensor

    # 1. Run Alembic migrations
    await run_migrations()

    # 2. Seed admin user
    async with async_session() as db:
        await auth.seed_admin(db)

    # 3. Seed sensor registry
    async with async_session() as db:
        await sensors.seed_sensor_registry(db)

    # 3b. Seed truck fleet (15 trucks across 3 depots)
    async with async_session() as db:
        await trucks.seed_truck_fleet(db)

    # 4. Load sensors from DB for prediction seed history
    async with async_session() as db:
        result = await db.execute(select(Sensor))
        sensors_list = [s.to_dict() for s in result.scalars().all()]

    # 5. Generate seed history + train models (in-memory)
    from app.services.prediction import generate_seed_history, train_initial_model
    generate_seed_history(sensors_list)
    train_initial_model()

    from app.services.truck_prediction import train_initial_model as train_truck_model
    train_truck_model()


@app.get("/health")
async def health_check():
    return {"status": "ok"}
