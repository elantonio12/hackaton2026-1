"""
API REST con FastAPI para controlar el simulador IoT.

Endpoints:
  GET  /                    → Info del API
  POST /simulacion/iniciar  → Inicia simulación
  GET  /sensores             → Lista sensores
  GET  /sensores/{id}        → Detalle sensor
  GET  /estadisticas         → Estadísticas globales
  GET  /alertas              → Lista de alertas
  GET  /datos/csv            → Descarga CSV
  GET  /estado               → Estado actual de todos los sensores
"""

from typing import Optional

# ─── Nota: FastAPI debe instalarse con pip install fastapi uvicorn ───
# Este módulo se importa solo cuando se ejecuta el servidor API.
# La simulación principal funciona sin FastAPI.

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    FASTAPI_DISPONIBLE = True
except ImportError:
    FASTAPI_DISPONIBLE = False

from .config import API_CONFIG, SIM_CONFIG, TipoRecolector, TipoDesperdicio, ZONAS_CDMX
from .simulacion import MotorSimulacion

# Instancia global del motor de simulación
motor: Optional[MotorSimulacion] = None


def crear_app() -> "FastAPI":
    """Crea y configura la aplicación FastAPI."""
    if not FASTAPI_DISPONIBLE:
        raise ImportError(
            "FastAPI no está instalado. "
            "Instalar con: pip install fastapi uvicorn"
        )

    app = FastAPI(
        title=API_CONFIG["title"],
        description=API_CONFIG["description"],
        version=API_CONFIG["version"],
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    global motor
    motor = MotorSimulacion()

    # ── Endpoints ────────────────────────────────────────────────────────

    @app.get("/")
    async def raiz():
        return {
            "nombre": API_CONFIG["title"],
            "version": API_CONFIG["version"],
            "estado": "activo",
            "endpoints": [
                "/simulacion/iniciar",
                "/sensores",
                "/estadisticas",
                "/alertas",
                "/datos/csv",
                "/estado",
            ],
        }

    @app.post("/simulacion/iniciar")
    async def iniciar_simulacion(
        n_sensores: int = Query(10, ge=1, le=100),
        dias: int = Query(90, ge=1, le=365),
        seed: int = Query(42, ge=0),
    ):
        global motor
        motor = MotorSimulacion(seed=seed, dias_simulacion=dias)
        motor.crear_sensores_predeterminados(n_sensores)
        stats = motor.ejecutar()

        # Exportar datos
        motor.exportar_csv()
        motor.exportar_alertas()
        motor.exportar_estadisticas()

        return {
            "estado": "completado",
            "estadisticas": stats,
        }

    @app.get("/sensores")
    async def listar_sensores():
        if not motor or not motor.sensores:
            raise HTTPException(404, "No hay sensores. Inicie la simulación primero.")

        return [
            {
                "sensor_id": s.sensor_id,
                "zona": s.zona.nombre,
                "tipo_recolector": s.tipo_recolector.value,
                "tipo_desperdicio": s.tipo_desperdicio.value,
                "capacidad_litros": s.capacidad_litros,
                "nivel_actual_pct": s.nivel_llenado_pct,
                "ciclos_llenado": s.ciclos_llenado,
                "total_lecturas": len(s.historial),
            }
            for s in motor.sensores
        ]

    @app.get("/sensores/{sensor_id}")
    async def detalle_sensor(sensor_id: str):
        if not motor:
            raise HTTPException(404, "Simulación no iniciada")

        sensor = next((s for s in motor.sensores if s.sensor_id == sensor_id), None)
        if not sensor:
            raise HTTPException(404, f"Sensor {sensor_id} no encontrado")

        return {
            "sensor_id": sensor.sensor_id,
            "zona": sensor.zona.nombre,
            "tipo_recolector": sensor.tipo_recolector.value,
            "nivel_actual": sensor.nivel_llenado_pct,
            "historial_ultimas_10": [
                {
                    "timestamp": l.timestamp.isoformat(),
                    "nivel_pct": l.nivel_llenado_pct,
                    "alerta": l.alerta,
                }
                for l in sensor.historial[-10:]
            ],
        }

    @app.get("/estadisticas")
    async def obtener_estadisticas():
        if not motor or not motor.estadisticas:
            raise HTTPException(404, "No hay estadísticas. Ejecute la simulación primero.")
        return motor.estadisticas

    @app.get("/alertas")
    async def obtener_alertas(limit: int = Query(50, ge=1, le=1000)):
        if not motor:
            raise HTTPException(404, "Simulación no iniciada")
        return motor.alertas[-limit:]

    @app.get("/estado")
    async def estado_actual():
        if not motor:
            raise HTTPException(404, "Simulación no iniciada")
        return motor.obtener_estado_actual()

    @app.get("/datos/csv")
    async def descargar_csv():
        import os
        ruta = "data/historial/sensores_historico.csv"
        if not os.path.exists(ruta):
            raise HTTPException(404, "CSV no generado. Ejecute la simulación primero.")
        return FileResponse(ruta, media_type="text/csv", filename="sensores_historico.csv")

    return app
