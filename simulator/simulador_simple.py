#!/usr/bin/env python3
"""
Simulador IoT Simplificado - Versión Reducida
Genera token único por sensor y envía alertas al 80% de capacidad.

Uso:
    python3 simulador_simple.py
    
Características:
    - Token único (32 caracteres) por sensor
    - Alertas solo cuando alcanza 80% de capacidad
    - Compatible con API REST o MQTT
    - Exporta reportes JSON
"""

import uuid
import json
import time
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import random

# ════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(levelname)-8s │ %(message)s'
)
logger = logging.getLogger(__name__)


class EstadoSensor(Enum):
    NORMAL = "NORMAL"
    ADVERTENCIA = "ADVERTENCIA"
    CRITICO = "CRITICO"


class TipoRecolector(Enum):
    PAPELERA = "Papelera"
    BOTE_BASURA = "Bote de Basura"
    CONTENEDOR_MIXTO = "Contenedor Mixto"
    DUMPSTER = "Dumpster"


ZONAS_CDMX = [
    "Colonia Roma", "Polanco", "Coyoacán Centro", "Tepito", "Santa Fe",
    "Xochimilco", "Iztapalapa Centro", "Condesa", "Narvarte", "Vallejo Industrial"
]

CAPACIDADES = {
    TipoRecolector.PAPELERA: 50,
    TipoRecolector.BOTE_BASURA: 120,
    TipoRecolector.CONTENEDOR_MIXTO: 240,
    TipoRecolector.DUMPSTER: 1100,
}


# ════════════════════════════════════════════════════════════════
# MODELOS
# ════════════════════════════════════════════════════════════════

@dataclass
class Alerta:
    """Modelo de alerta generada al alcanzar 80%"""
    tipo: str = "NIVEL_CRITICO_80"
    sensor_id: str = ""
    token: str = ""
    zona: str = ""
    nivel_pct: float = 0.0
    capacidad_litros: int = 0
    litros_actuales: float = 0.0
    timestamp: str = ""
    accion_sugerida: str = "RECOLECTAR"


@dataclass
class EstadoSensorData:
    """Estado actual de un sensor"""
    sensor_id: str
    token: str
    zona: str
    tipo: str
    nivel_llenado: float
    capacidad_litros: int
    litros_actuales: float
    alerta_activa: bool
    temperatura_c: float
    humedad_pct: float
    ciclos: int
    fecha_ultimo_vaciado: str


# ════════════════════════════════════════════════════════════════
# SENSOR SIMPLIFICADO
# ════════════════════════════════════════════════════════════════

class SensorIoTSimple:
    """
    Sensor IoT simplificado.
    - Genera token único de 32 caracteres
    - Simula llenado realista
    - Alerta SOLO una vez al alcanzar 80%
    """

    def __init__(
        self,
        sensor_id: str,
        zona: str,
        tipo: TipoRecolector,
    ):
        self.sensor_id = sensor_id
        self.zona = zona
        self.tipo = tipo
        self.capacidad_litros = CAPACIDADES[tipo]

        # Token único basado en timestamp + random
        self._generar_token()

        # Estado
        self.nivel_llenado = random.uniform(5, 30)  # Inicia entre 5-30%
        self.alerta_80_enviada = False  # Flag para enviar alerta solo una vez
        self.fecha_ultimo_vaciado = datetime.now()
        self.ciclos_llenado = 0

        # Sensores ambientales
        self.temperatura = 15.0 + random.uniform(-5, 10)
        self.humedad = 40.0 + random.uniform(-10, 30)

        logger.info(
            f"✓ Sensor creado: {sensor_id:12s} | {zona:20s} | "
            f"{tipo.value:18s} | Token: {self.token[:16]}..."
        )

    def _generar_token(self) -> None:
        """Genera token único de 32 caracteres"""
        timestamp = hex(int(time.time() * 1000))[2:].upper()
        random_part = uuid.uuid4().hex.upper()[:20]
        self.token = f"TKN-{timestamp}-{random_part}"[:32]

    def actualizar(self) -> Optional[Alerta]:
        """
        Actualiza el estado del sensor y retorna Alerta si alcanza 80%.

        Returns:
            Alerta si se alcanza 80% y no se ha enviado aún
            None si no hay nueva alerta
        """
        # Simular incremento de llenado
        hora = datetime.now().hour
        tasa_base = 2.5  # % por ciclo

        # Factor horario
        if 6 <= hora < 12:
            tasa_base *= 1.2  # Mañana
        elif 12 <= hora < 18:
            tasa_base *= 1.3  # Tarde
        elif 18 <= hora < 24:
            tasa_base *= 1.5  # Noche
        else:
            tasa_base *= 0.3  # Madrugada

        # Variabilidad aleatoria
        variabilidad = random.uniform(0.8, 1.2)
        incremento = tasa_base * variabilidad

        # Actualizar nivel
        self.nivel_llenado = min(100.0, self.nivel_llenado + incremento)

        # Actualizar condiciones ambientales
        self.temperatura = 15.0 + random.uniform(-5, 10) + (5 * math.sin(hora / 12))
        self.humedad = 40.0 + random.uniform(-10, 30)

        # Vaciar si alcanza 100%
        if self.nivel_llenado >= 100.0:
            self._vaciar()

        # Generar alerta si alcanza 80% (solo una vez)
        alerta = None
        if self.nivel_llenado >= 80.0 and not self.alerta_80_enviada:
            self.alerta_80_enviada = True
            alerta = Alerta(
                sensor_id=self.sensor_id,
                token=self.token,
                zona=self.zona,
                nivel_pct=round(self.nivel_llenado, 1),
                capacidad_litros=self.capacidad_litros,
                litros_actuales=round(
                    (self.nivel_llenado / 100) * self.capacidad_litros, 1
                ),
                timestamp=datetime.now().isoformat() + "Z",
            )

        return alerta

    def _vaciar(self) -> None:
        """Simula el vaciado del contenedor"""
        self.nivel_llenado = 5.0
        self.alerta_80_enviada = False
        self.fecha_ultimo_vaciado = datetime.now()
        self.ciclos_llenado += 1
        logger.debug(f"🗑️  Sensor {self.sensor_id} vaciado (ciclo #{self.ciclos_llenado})")

    def obtener_estado(self) -> EstadoSensorData:
        """Retorna el estado actual del sensor"""
        return EstadoSensorData(
            sensor_id=self.sensor_id,
            token=self.token,
            zona=self.zona,
            tipo=self.tipo.value,
            nivel_llenado=round(self.nivel_llenado, 1),
            capacidad_litros=self.capacidad_litros,
            litros_actuales=round(
                (self.nivel_llenado / 100) * self.capacidad_litros, 1
            ),
            alerta_activa=self.nivel_llenado >= 80,
            temperatura_c=round(self.temperatura, 1),
            humedad_pct=round(self.humedad, 1),
            ciclos=self.ciclos_llenado,
            fecha_ultimo_vaciado=self.fecha_ultimo_vaciado.isoformat(),
        )


# ════════════════════════════════════════════════════════════════
# MOTOR DE SIMULACIÓN
# ════════════════════════════════════════════════════════════════

class MotorSimulacionSimple:
    """Motor de simulación simplificado"""

    def __init__(self, n_sensores: int = 10):
        self.sensores: List[SensorIoTSimple] = []
        self.alertas: List[Dict[str, Any]] = []
        self.n_sensores = n_sensores

        self._crear_sensores()

    def _crear_sensores(self) -> None:
        """Crea los sensores"""
        logger.info(f"\n{'='*70}")
        logger.info(f"  Creando {self.n_sensores} sensores...")
        logger.info(f"{'='*70}\n")

        for i in range(self.n_sensores):
            sensor_id = f"SENS-{str(i+1).zfill(3)}"
            zona = random.choice(ZONAS_CDMX)
            tipo = random.choice(list(TipoRecolector))

            sensor = SensorIoTSimple(sensor_id, zona, tipo)
            self.sensores.append(sensor)

    def ejecutar_ciclo(self) -> None:
        """Ejecuta un ciclo de simulación"""
        for sensor in self.sensores:
            alerta = sensor.actualizar()
            if alerta:
                self.alertas.append(asdict(alerta))
                logger.warning(
                    f"🚨 ALERTA GENERADA - {alerta.sensor_id} | "
                    f"{alerta.zona} | {alerta.nivel_pct}% | Token: {alerta.token[:20]}..."
                )

    def obtener_resumen(self) -> Dict[str, Any]:
        """Retorna un resumen de la simulación"""
        estados = [sensor.obtener_estado() for sensor in self.sensores]

        nivel_promedio = sum(s.nivel_llenado for s in self.sensores) / len(self.sensores) \
            if self.sensores else 0

        criticos = sum(1 for s in self.sensores if s.nivel_llenado >= 80)

        return {
            "timestamp": datetime.now().isoformat(),
            "sensores_activos": len(self.sensores),
            "total_alertas": len(self.alertas),
            "nivel_promedio_pct": round(nivel_promedio, 1),
            "sensores_criticos": criticos,
            "estados_sensores": [asdict(e) for e in estados],
            "alertas_recientes": self.alertas[-10:],  # Últimas 10 alertas
        }

    def exportar_json(self, ruta: str = "data/sensores_report.json") -> str:
        """Exporta los datos a JSON"""
        import os
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)

        datos = {
            "metadata": {
                "fecha_exportacion": datetime.now().isoformat(),
                "total_sensores": len(self.sensores),
                "total_alertas": len(self.alertas),
            },
            "sensores": [asdict(s.obtener_estado()) for s in self.sensores],
            "alertas": self.alertas,
        }

        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 JSON exportado: {ruta}")
        return ruta

    def mostrar_resumen(self) -> None:
        """Muestra un resumen formateado en consola"""
        resumen = self.obtener_resumen()

        print("\n" + "="*70)
        print("  📊 RESUMEN DE SIMULACIÓN")
        print("="*70)
        print(f"  Sensores Activos:     {resumen['sensores_activos']}")
        print(f"  Alertas Generadas:    {resumen['total_alertas']}")
        print(f"  Nivel Promedio:       {resumen['nivel_promedio_pct']}%")
        print(f"  Sensores Críticos:    {resumen['sensores_criticos']}")
        print("="*70)

        print("\n  📍 ESTADO DE SENSORES (Top 5 más llenos):\n")
        estados_ordenados = sorted(
            resumen['estados_sensores'],
            key=lambda x: x['nivel_llenado'],
            reverse=True
        )[:5]

        for estado in estados_ordenados:
            estado_str = "🟢 OK" if estado['nivel_llenado'] < 60 else \
                        "🟡 ADVERTENCIA" if estado['nivel_llenado'] < 80 else \
                        "🔴 CRÍTICO"

            print(
                f"  {estado['sensor_id']:12s} | "
                f"{estado['zona']:20s} | "
                f"{estado['nivel_llenado']:6.1f}% | "
                f"{estado_str}"
            )

        if resumen['alertas_recientes']:
            print("\n  🚨 ÚLTIMAS ALERTAS GENERADAS:\n")
            for alerta in resumen['alertas_recientes'][-5:]:
                print(
                    f"  {alerta['sensor_id']:12s} | "
                    f"{alerta['zona']:20s} | "
                    f"{alerta['nivel_pct']}% | "
                    f"Token: {alerta['token'][:20]}..."
                )

        print("\n" + "="*70 + "\n")


# ════════════════════════════════════════════════════════════════
# SERVIDOR API OPCIONAL (FastAPI)
# ════════════════════════════════════════════════════════════════

def crear_api_rest(motor: MotorSimulacionSimple):
    """
    Crea un servidor FastAPI opcional.
    Instalar con: pip install fastapi uvicorn
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.middleware.cors import CORSMiddleware

        app = FastAPI(
            title="IoT Recolección API",
            description="API para simulador de sensores IoT",
            version="1.0.0"
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/")
        async def raiz():
            return {"status": "activo", "version": "1.0.0"}

        @app.get("/sensores")
        async def listar_sensores():
            return {
                "total": len(motor.sensores),
                "sensores": [asdict(s.obtener_estado()) for s in motor.sensores]
            }

        @app.get("/sensores/{sensor_id}")
        async def detalle_sensor(sensor_id: str):
            sensor = next((s for s in motor.sensores if s.sensor_id == sensor_id), None)
            if not sensor:
                return JSONResponse({"error": "Sensor no encontrado"}, status_code=404)
            return asdict(sensor.obtener_estado())

        @app.get("/alertas")
        async def obtener_alertas():
            return {
                "total": len(motor.alertas),
                "alertas": motor.alertas[-50:]
            }

        @app.post("/ciclo")
        async def ejecutar_ciclo():
            motor.ejecutar_ciclo()
            return motor.obtener_resumen()

        @app.get("/resumen")
        async def obtener_resumen():
            return motor.obtener_resumen()

        return app

    except ImportError:
        logger.warning("FastAPI no instalado. Ejecutar: pip install fastapi uvicorn")
        return None


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    """Función principal"""
    print("\n" + "🗑️ " * 25)
    print("  SIMULADOR IoT SIMPLIFICADO - Recolección de Residuos")
    print("  Token Único + Alertas al 80%")
    print("🗑️ " * 25 + "\n")

    # Crear motor
    motor = MotorSimulacionSimple(n_sensores=12)

    # Ejecutar ciclos de simulación
    print("▶️  Ejecutando simulación (10 ciclos)...\n")
    for ciclo in range(10):
        print(f"  Ciclo {ciclo + 1}/10")
        motor.ejecutar_ciclo()
        time.sleep(1)  # Esperar 1 segundo entre ciclos

    # Mostrar resumen
    motor.mostrar_resumen()

    # Exportar datos
    motor.exportar_json("data/sensores_report.json")

    # Crear API (opcional)
    print("💡 Para iniciar servidor API REST:")
    print("   pip install fastapi uvicorn")
    print("   python3 -c \"from simulador_simple import *; app = crear_api_rest(MotorSimulacionSimple()); \\")
    print("   import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)\"\n")


if __name__ == "__main__":
    main()
