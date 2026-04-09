# Análisis de Competencia — EcoRuta

## 1. Competidores directos (Smart Waste Management con IoT + Rutas)

### Globales

| Empresa | País | Qué hacen | Clientes | Diferencia con EcoRuta |
|---------|------|-----------|----------|----------------------|
| **Sensoneo** | Eslovaquia | Sensores de llenado + software de rutas + analytics | Buenos Aires (4,500 sensores), ciudades EU | Solo hardware+software, sin IA generativa para comunicación |
| **Bigbelly** | USA | Contenedores inteligentes solares con compactación + plataforma CLEAN | Ciudades de USA, universidades | Requiere comprar sus contenedores propietarios (~$4,000 USD c/u) |
| **Enevo** (adquirida por REEN) | Noruega/USA | Sensores + plataforma cloud + optimización de rutas | Municipios EU, operadores privados | Software genérico, sin adaptación a LATAM ni IA generativa |
| **Compology** (adquirida por RoadRunner) | USA | Cámaras en contenedores + analítica visual | Operadores USA | Solo mercado USA, enfocado en reciclaje comercial |
| **Ecube Labs** | Corea del Sur | Contenedores solares (CleanCUBE) + sensores (CleanFLEX) + plataforma | Global | Hardware costoso, sin presencia LATAM |
| **Urbetrack** | Argentina | IoT + telemetría + optimización de rutas sanitarias | Buenos Aires, ciudades LATAM | El competidor más cercano en LATAM. Consultoría + software. No tiene IA generativa. |
| **SmartEnds** | Bélgica | Sensores VisnLine + software de gestión | Ciudades EU | Solo Europa, sin presencia LATAM |

### En México

| Empresa | Qué hacen | Limitaciones |
|---------|-----------|-------------|
| **SIMEPRODE** (Nuevo León) | Gestión de residuos estatal | Organismo público, no es solución tecnológica replicable |
| **Recicla Electrónicos / Red Ambiental** | Recolección privada especializada | Sin componente IoT ni optimización de rutas con IA |
| **Municipios (operación directa)** | Recolección con rutas fijas manuales | Sin tecnología, sin datos en tiempo real |

**No existe un competidor directo en México que combine IoT + optimización de rutas + IA generativa.**

---

## 2. Competidores indirectos

| Tipo | Ejemplos | Por qué compiten indirectamente |
|------|----------|-------------------------------|
| Software de gestión de flotas | Geotab, Samsara, Fleet Complete | Optimizan flotas en general pero no entienden llenado de contenedores |
| GPS/Telemetría vehicular | Urbetrack (parcial), Rastrea | Solo rastrean vehículos, no contenedores |
| Apps de reporte ciudadano | 072 CDMX, Decide CDMX | Solo reportan, no optimizan |
| Consultoras de residuos | KPMG, Deloitte (sustentabilidad) | Consultoría, no producto tecnológico |

---

## 3. Tabla comparativa: EcoRuta vs. Competencia

| Característica | EcoRuta | Sensoneo | Bigbelly | Urbetrack | Enevo |
|---------------|---------|----------|----------|-----------|-------|
| Sensores IoT (llenado) | Simulados (MVP) / Compatibles | Propios | Propios (integrados en contenedor) | Integración terceros | Propios |
| Optimización de rutas con IA | OR-Tools + TSP | Algoritmo propio | Básico | Algoritmos propios | Sí |
| IA Generativa (lenguaje natural) | IBM Watsonx | No | No | No | No |
| Instrucciones en lenguaje natural para conductores | Si | No | No | No | No |
| Reportes ciudadanos integrados | Si (app móvil) | No | No | No | No |
| Predicción de llenado (ML) | Si (MLP) | Si | No | Parcial | Si |
| Enfocado en LATAM / México | Si | No (solo piloto Buenos Aires) | No | Si (Argentina) | No |
| Costo de entrada | Bajo (SaaS, sin hardware propietario) | Alto (sensores + licencia) | Muy alto ($4K/contenedor) | Medio | Alto |
| Escalabilidad cloud | IBM Cloud | Cloud propio | Cloud propio | Cloud | Cloud |
| Idioma español nativo | Si | No | No | Si | No |
| Open source / adaptable | Si (hackathon) | No | No | No | No |

---

## 4. Diferenciadores clave de EcoRuta

### 1. IA Generativa como interfaz humana
Ningún competidor usa IA generativa para traducir resultados técnicos en instrucciones claras para cada perfil de usuario. Esto hace que el sistema sea **usable por personas sin formación técnica** — que son precisamente los conductores y gestores que toman decisiones operativas.

### 2. Sin dependencia de hardware propietario
A diferencia de Bigbelly o Ecube Labs, EcoRuta no requiere que el cliente compre contenedores especiales de $4,000 USD. Funciona con **cualquier sensor IoT estándar** o incluso con datos de reportes ciudadanos.

### 3. Diseñado para el contexto mexicano
- Datos geoespaciales de CDMX.
- Español nativo.
- Entiende la estructura de alcaldías, concesionarios y servicio público municipal.
- Adaptado a las necesidades regulatorias (separación obligatoria 2026).

### 4. Triple fuente de datos
Mientras la competencia solo usa sensores, EcoRuta integra:
1. Sensores IoT (datos objetivos)
2. Reportes ciudadanos (anomalías no detectables por sensores)
3. Datos históricos por zona y día (patrones predictivos)

### 5. Costo de entrada bajo
Modelo SaaS sin inversión en hardware propietario = barrera de entrada mínima para alcaldías con presupuesto limitado.

---

## 5. Matriz de posicionamiento

```
                    ALTO COSTO
                        │
         Bigbelly       │       Ecube Labs
         (contenedores  │       (hardware
          propietarios) │        premium)
                        │
  BAJA ─────────────────┼─────────────────── ALTA
  INTELIGENCIA          │              INTELIGENCIA
                        │
         Urbetrack      │       ★ EcoRuta ★
         (telemetría    │       (IoT + IA Gen +
          + rutas)      │        bajo costo)
                        │
                    BAJO COSTO
```

---

## 6. Conclusión para el pitch

> "Existen soluciones de smart waste management en el mundo, pero ninguna combina optimización de rutas con IA generativa para comunicación humana, y ninguna está diseñada para el contexto mexicano. Las opciones globales requieren hardware costoso y no hablan español. **EcoRuta es la primera solución pensada desde México, para México**, con tecnología IBM de clase mundial."

---

## Fuentes
- [Sensoneo - Smart Waste Buenos Aires](https://www.sensoneo.com/success-stories/smart-waste-deployments-south-america/)
- [Urbetrack - Sanitation & Smart City](https://urbetrack.com/en/sanitation-smart-city)
- [IMARC - Top Smart Waste Companies](https://www.imarcgroup.com/top-smart-waste-management-companies)
- [Verified Market Research - Top Companies](https://www.verifiedmarketresearch.com/blog/top-smart-waste-management-companies/)
- [Bigbelly - Harvard Case Study](https://d3.harvard.edu/platform-rctom/submission/bigbelly-whetting-our-appetite-for-smarter-waste-management-business-models/)
- [Mordor Intelligence - Smart Waste Market](https://www.mordorintelligence.com/industry-reports/smart-waste-management-market)
