from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    sub: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="citizen")
    provider: Mapped[str] = mapped_column(String(50))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}

    def to_public_dict(self) -> dict:
        d = self.to_dict()
        d.pop("password_hash", None)
        return d


class Sensor(Base):
    __tablename__ = "sensors"

    sensor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    container_id: Mapped[str] = mapped_column(String(100), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(50))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(50), default="activo")

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class ContainerReading(Base):
    __tablename__ = "container_readings"

    container_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    fill_level: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(50))
    timestamp: Mapped[str] = mapped_column(String(50))

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    zone: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class Collector(Base):
    __tablename__ = "collectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255))
    empleado_id: Mapped[str] = mapped_column(String(100))
    zona: Mapped[str] = mapped_column(String(50))
    camion_id: Mapped[str] = mapped_column(String(100))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class ProblemReport(Base):
    __tablename__ = "problem_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(50))
    tipo_problema: Mapped[str] = mapped_column(String(50))
    descripcion: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(50), default="recibido")

    def to_dict(self) -> dict:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class Truck(Base):
    """Operational truck. Position is updated in near-real-time by the
    truck simulator. `assigned_user_sub` lets the recolector frontend
    look up its own truck via /trucks/me/route.
    """
    __tablename__ = "trucks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "TRK-01"
    name: Mapped[str] = mapped_column(String(255))
    zone: Mapped[str] = mapped_column(String(50), index=True)  # primary alcaldia
    capacity_m3: Mapped[float] = mapped_column(Float, default=12.0)
    current_load_m3: Mapped[float] = mapped_column(Float, default=0.0)
    depot_lat: Mapped[float] = mapped_column(Float)
    depot_lon: Mapped[float] = mapped_column(Float)
    current_lat: Mapped[float] = mapped_column(Float)
    current_lon: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="idle", index=True)
    # idle | en_route | collecting | returning | offline
    current_route_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_user_sub: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        d = {c.key: getattr(self, c.key) for c in self.__table__.columns}
        # JSON-friendly timestamp
        if isinstance(d.get("updated_at"), datetime):
            d["updated_at"] = d["updated_at"].isoformat()
        return d


class Route(Base):
    """Active or historical truck route. `stops` and `polyline_geojson`
    are stored as JSONB so the frontend can read the full route in a
    single GET without joins.
    """
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    truck_id: Mapped[str] = mapped_column(String(50), index=True)
    stops: Mapped[list] = mapped_column(JSON)  # [{order, container_id, latitude, longitude, fill_level, status, distance_along_route_m}]
    polyline_geojson: Mapped[dict] = mapped_column(JSON)  # GeoJSON LineString
    distance_km: Mapped[float] = mapped_column(Float)
    duration_min: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    # active | completed | aborted
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_dict(self) -> dict:
        d = {c.key: getattr(self, c.key) for c in self.__table__.columns}
        for k in ("started_at", "completed_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        return d
