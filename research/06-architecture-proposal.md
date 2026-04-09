# Arquitectura Técnica — EcoRuta (para presentación)

## 1. Visión general: 4 capas

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPA DE PRESENTACIÓN                      │
│  Dashboard operativo (Astro + Tailwind)  │  App móvil (PWA) │
│  Mapa interactivo  │  Panel de conductor  │  Reportes        │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTPS / REST API
┌────────────────────────────▼────────────────────────────────┐
│                  CAPA DE IA + OPTIMIZACIÓN                   │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Motor de     │  │ Predicción   │  │ Agente IA         │  │
│  │ Rutas        │  │ ML (MLP)     │  │ (IBM Watsonx)     │  │
│  │ (OR-Tools +  │  │ Nivel de     │  │ Lenguaje natural: │  │
│  │  TSP/Grafo)  │  │ llenado      │  │ - Instrucciones   │  │
│  │              │  │ futuro       │  │ - Reportes        │  │
│  │              │  │              │  │ - Alertas         │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│              CAPA DE PROCESAMIENTO EN LA NUBE                │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ FastAPI      │  │ PostgreSQL   │  │ IBM Cloud         │  │
│  │ (Backend)    │  │ + PostGIS    │  │ (Watsonx API)     │  │
│  │ REST API v1  │  │ (Geoespacial)│  │                   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  CAPA DE CAPTURA DE DATOS                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Sensores IoT │  │ Reportes     │  │ Datos históricos  │  │
│  │ (50 contene- │  │ ciudadanos   │  │ (patrones por     │  │
│  │  dores, 3    │  │ (App móvil)  │  │  zona y día)      │  │
│  │  zonas CDMX) │  │              │  │                   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Stack tecnológico detallado

| Capa | Tecnología | Justificación |
|------|-----------|---------------|
| **Frontend** | Astro 6 + Tailwind CSS 4 | Framework moderno, SSR, rendimiento óptimo |
| **PWA** | Vite PWA Plugin | App instalable, funciona offline — crítico para conductores |
| **Backend** | FastAPI (Python) | Async nativo, alto rendimiento, documentación automática (Swagger) |
| **Base de datos** | PostgreSQL 16 + PostGIS | Estándar de la industria para datos geoespaciales |
| **ORM** | SQLAlchemy 2.0 + AsyncPG | Queries async para alta concurrencia |
| **Optimización** | Google OR-Tools + NetworkX | OR-Tools: motor de optimización industrial. NetworkX: modelado de grafos viales |
| **ML/Predicción** | Scikit-learn (MLP) | Perceptrón multicapa para predecir llenado futuro |
| **IA Generativa** | IBM Watsonx | IA enterprise-grade, confiable para servicios públicos |
| **Auth** | JWT + Google OAuth | Seguridad estándar, login fácil para usuarios |
| **Infraestructura** | Docker + Docker Compose | Contenedores para despliegue reproducible |
| **CI/CD** | GitHub Actions | Integración y despliegue continuo |
| **Deploy** | Astro en Cloudflare Pages, FastAPI en VPS | Split deploy: frontend CDN global + backend dedicado |

---

## 3. Flujo de datos (para explicar al jurado)

### Antes de la ruta (automático, cada 10 segundos)
```
Sensores IoT ──→ API /sensors/ ──→ PostgreSQL + PostGIS
                                        │
                                        ▼
                                   Predicción ML
                                   (¿cuándo se llenará?)
                                        │
                                        ▼
                                   Motor OR-Tools
                                   (ruta óptima TSP)
                                        │
                                        ▼
                                   Watsonx IA Gen
                                   (instrucciones en español)
                                        │
                                        ▼
                                   Dashboard + App conductor
```

### Durante la ruta (tiempo real)
```
Sensor detecta cambio ──→ Recalculo de ruta ──→ Notificación al conductor
                                                 "Hay un contenedor al 95%
                                                  a 200m de tu posición.
                                                  ¿Deseas desviarte?"
```

### Al cierre del turno
```
Datos de la jornada ──→ Watsonx ──→ Reporte ejecutivo automático
                                    "Hoy se recorrieron 360 km vs 480 km
                                     de la ruta estándar. Ahorro: 25%.
                                     CO₂ evitado: 129 kg."
```

---

## 4. API — Endpoints principales

| Endpoint | Función | Usuario |
|----------|---------|---------|
| `POST /api/v1/sensors/` | Ingesta de datos IoT | Sensores (API key) |
| `GET /api/v1/containers/` | Estado de contenedores | Dashboard |
| `POST /api/v1/routes/optimize` | Generar ruta óptima | Gestor/Automático |
| `GET /api/v1/predictions/` | Predicción de llenado | Dashboard |
| `GET /api/v1/metrics/` | Métricas de eficiencia | Gestor municipal |
| `GET /api/v1/reports/` | Reportes ejecutivos | Gestor municipal |
| `POST /api/v1/auth/` | Autenticación | Todos |

Documentación interactiva disponible en `/docs` (Swagger UI).

---

## 5. ¿Por qué IBM Watsonx? (Justificación para el jurado)

| Criterio | IBM Watsonx | Alternativas (OpenAI, etc.) |
|----------|------------|----------------------------|
| **Diseñado para enterprise** | Si — compliance, auditoría, SLA | Parcial |
| **Confiable para gobierno** | Si — IBM tiene contratos con gobiernos a nivel mundial | No probado en gobierno MX |
| **Integración IoT nativa** | Si — ecosystem IBM Cloud | Requiere integraciones adicionales |
| **Privacidad de datos** | Datos no se usan para entrenar modelos | Depende del plan |
| **Track del hackathon** | Requisito del track IBM | No aplica |

---

## 6. Resiliencia y tolerancia a fallos

```
¿Qué pasa si...?

Watsonx no responde    → Plantillas de texto predefinidas (fallback)
Sensores fallan        → Datos históricos + reportes ciudadanos
Optimizador es lento   → Límite de 50 contenedores, respuesta < 5s
Sin internet en demo   → Mapa en caché, lógica local
```

> **Principio: cada módulo opera de forma autónoma.** Siempre hay algo funcional ante el jurado.

---

## 7. Escalabilidad

| Escenario | Contenedores | Infraestructura | Tiempo de respuesta |
|-----------|-------------|-----------------|-------------------|
| MVP (demo) | 50 | 1 VPS + DB local | < 2s |
| 1 alcaldía | 200 | 1 VPS + DB managed | < 3s |
| CDMX completa | 5,000+ | Cluster + DB replicada | < 5s |
| Multi-ciudad | 20,000+ | Multi-región IBM Cloud | < 5s |

PostGIS y OR-Tools escalan linealmente. Solo se agregan sensores y capacidad de cómputo.

---

## 8. Para el pitch (en 60 segundos)

> "La arquitectura tiene 4 capas. Abajo, sensores IoT y reportes ciudadanos alimentan datos en tiempo real. En la nube, PostgreSQL con PostGIS almacena todo con capacidad geoespacial. El motor de IA usa OR-Tools para calcular la ruta óptima y Watsonx para traducirlo a instrucciones claras en español. Arriba, un dashboard muestra todo en un mapa interactivo. Cada capa es independiente — si una falla, las demás siguen funcionando. Y todo corre en contenedores Docker con CI/CD."
