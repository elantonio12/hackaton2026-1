from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.models.schemas import Collector, CollectorCreate, CollectorUpdate

router = APIRouter()

# In-memory store igual que containers.py (para la demo)
collectors_db: dict[int, dict] = {}
counter = 1

@router.post("/", response_model=Collector)
async def create_collector(collector: CollectorCreate):
    """Registrar un nuevo recolector."""
    global counter
    now = datetime.now()
    new_collector = {
        "id": counter,
        **collector.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    collectors_db[counter] = new_collector
    counter += 1
    return new_collector

@router.get("/", response_model=list[Collector])
async def get_collectors(zona: str = None, activo: bool = None):
    """Obtener todos los recolectores. Filtra por zona o estado."""
    result = list(collectors_db.values())
    if zona:
        result = [c for c in result if c["zona"] == zona]
    if activo is not None:
        result = [c for c in result if c["activo"] == activo]
    return result

@router.get("/{collector_id}", response_model=Collector)
async def get_collector(collector_id: int):
    """Obtener un recolector por ID."""
    if collector_id not in collectors_db:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    return collectors_db[collector_id]

@router.put("/{collector_id}", response_model=Collector)
async def update_collector(collector_id: int, updates: CollectorUpdate):
    """Actualizar datos de un recolector."""
    if collector_id not in collectors_db:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    collector = collectors_db[collector_id]
    for field, value in updates.model_dump(exclude_unset=True).items():
        collector[field] = value
    collector["updated_at"] = datetime.now()
    return collector

@router.delete("/{collector_id}")
async def delete_collector(collector_id: int):
    """Eliminar un recolector."""
    if collector_id not in collectors_db:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    del collectors_db[collector_id]
    return {"status": "deleted", "id": collector_id}