# Guía de Pitch — EcoRuta

## Estructura recomendada para la presentación

---

### 1. Abrir con una pregunta que genere tensión

> **"¿Sabían que cada día la Ciudad de México envía más de 2,500 camiones recolectores a recorrer rutas que fueron diseñadas hace meses... sin saber si los contenedores están llenos o vacíos?"**

Alternativas de apertura:
- "¿Qué pasaría si pudiéramos evitar que un camión de basura recorra 120 kilómetros innecesarios cada día?"
- "La CDMX genera 12,700 toneladas de basura al día. ¿Y si les dijera que el sistema para recogerla no ha cambiado en décadas?"

**Por qué funciona:** El jurado conecta emocionalmente cuando se presenta una ineficiencia concreta que afecta a millones de personas.

---

### 2. Explicar el porqué — Comparar con otros sistemas de transporte

El transporte de personas ya se transformó con datos en tiempo real:
- **Uber/DiDi** optimizan rutas de transporte de pasajeros con IA y GPS en tiempo real.
- **Rappi/UberEats** calculan rutas dinámicas de entrega según demanda y ubicación.
- **Waze/Google Maps** redirigen millones de autos basándose en tráfico real.

**Pero la recolección de basura sigue operando como hace 30 años:** rutas fijas, horarios rígidos, sin datos de ocupación. Es el único sistema logístico urbano masivo que **no** se ha beneficiado de la revolución de datos.

> "Si ya optimizamos cómo nos movemos y cómo nos llega la comida... ¿por qué no optimizamos cómo se recoge nuestra basura?"

---

### 3. Vincular a una causa más grande

EcoRuta no es solo un optimizador de rutas. Contribuye a:

- **ODS 11 — Ciudades y Comunidades Sostenibles:** Ciudades inclusivas, seguras, resilientes y sostenibles.
- **ODS 13 — Acción por el Clima:** Reducción directa de emisiones de CO₂ (estimado ~129 kg/día por flota).
- **ODS 12 — Producción y Consumo Responsables:** Gestión eficiente de residuos urbanos.

> "No estamos construyendo una app. Estamos construyendo infraestructura inteligente para que las ciudades dejen de reaccionar y empiecen a anticiparse."

---

### 4. Exponer el problema con claridad y propósito

#### El problema en 3 datos:

| Dato | Fuente |
|------|--------|
| CDMX genera **12,700 toneladas** de basura diaria | SEDEMA / Excélsior 2025 |
| El gobierno destina **500 MDP** (2025-2026) solo en vehículos e infraestructura | Expansion 2025 |
| Las rutas actuales son **fijas y estáticas**, diseñadas con semanas de anticipación | INECC |

#### El dolor:
- Camiones recorren rutas completas aunque contenedores estén al 30% de capacidad.
- Zonas de alta densidad se desbordan antes de la recolección programada.
- No hay retroalimentación en tiempo real.
- **Resultado:** costos innecesarios, emisiones evitables, ciudadanos insatisfechos.

#### El propósito:
> "Convertir la recolección de basura de un servicio reactivo y costoso en un sistema inteligente, predictivo y medible."

---

### 5. Explicar con diagramas (sugerencias visuales)

#### Diagrama 1 — Antes vs. Después
```
ANTES (Sistema Actual)          DESPUÉS (EcoRuta)
┌─────────────────┐            ┌─────────────────────┐
│ Rutas fijas      │            │ Sensores IoT         │
│ Sin datos        │            │ Datos en tiempo real  │
│ Decisión manual  │     →      │ IA optimiza rutas     │
│ Viajes vacíos    │            │ Solo donde se necesita│
│ Sin métricas     │            │ Dashboard + KPIs      │
└─────────────────┘            └─────────────────────┘
```

#### Diagrama 2 — Flujo del sistema (para slide)
```
[Sensores IoT] → [Nube IBM Watsonx] → [Motor IA + Optimización] → [Dashboard/App]
      ↑                                                                    ↓
[Reportes ciudadanos]                                              [Conductores]
                                                                   [Gestores]
                                                                   [Ciudadanos]
```

#### Diagrama 3 — Impacto cuantificado (para slide de cierre)
```
50 contenedores × 3 zonas CDMX
        ↓
   ≥ 25% menos km recorridos
   ~129 kg CO₂ evitados/día
   18-25% ahorro en combustible
   < 5s generación de ruta
```

---

### 6. Estructura sugerida de slides

| # | Slide | Tiempo | Contenido clave |
|---|-------|--------|-----------------|
| 1 | Pregunta de apertura | 30s | Dato impactante + pregunta retórica |
| 2 | El problema | 1min | 3 datos duros, comparación con transporte |
| 3 | La causa mayor | 30s | ODS, visión de ciudad inteligente |
| 4 | Nuestra solución | 1min | Qué es, qué hace, diagrama de flujo |
| 5 | Arquitectura técnica | 1min | 4 capas, IBM Watsonx, IoT |
| 6 | Demo / Prototipo | 1-2min | Dashboard en vivo, mapa, métricas |
| 7 | Mercado y cliente | 45s | Quién paga, tamaño de mercado |
| 8 | Competencia y diferenciador | 30s | Tabla comparativa |
| 9 | Modelo de negocio | 45s | SaaS, recuperación de inversión |
| 10 | Impacto y KPIs | 30s | Métricas de cierre, visión a futuro |
| 11 | Equipo | 15s | Roles complementarios |
| 12 | Cierre + Call to action | 15s | Frase memorable |

---

### 7. Tips para responder al jurado

- **"¿Por qué IBM Watsonx y no otra IA?"** → Arquitectura enterprise-grade, integración nativa con IoT, confiabilidad para servicios públicos, escalabilidad elástica.
- **"¿Cómo escalan más allá de 50 contenedores?"** → La arquitectura está diseñada con PostGIS y OR-Tools que escalan linealmente. Solo se agregan sensores y el motor recalcula.
- **"¿Qué pasa si falla la IA?"** → Cada módulo opera de forma autónoma. El optimizador no depende de la IA generativa. Hay plantillas de respaldo.
- **"¿Quién paga por esto?"** → Modelo SaaS para alcaldías/concesionarios. El ahorro en combustible (18-25%) paga la suscripción.
