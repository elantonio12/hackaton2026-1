# Landing Page Design Spec -- EcoRuta

> Documento de diseno conceptual para la landing page de EcoRuta.
> Todo el copy esta en espanol (listo para implementar). Los datos provienen de los documentos de investigacion del equipo.

---

## Principios de diseno

- **Paleta:** Verde eco (#16a34a principal, #22c55e claro, #15803d oscuro), fondo claro #f9fafb, paneles blancos #ffffff, texto #111827 / #6b7280
- **Tipografia:** System font stack (sans-serif), ya definido en Tailwind como `font-sans`
- **Estilo visual:** Limpio, moderno, con espacio en blanco generoso. Paneles con bordes suaves (rounded-xl), sombras sutiles. Gradientes verdes en CTAs.
- **Responsive:** Mobile-first. Cada seccion debe funcionar en movil y escritorio.
- **Tono:** Profesional pero accesible. Datos concretos, no promesas vagas. Lenguaje que un gestor municipal entienda.

---

## Seccion 1: Hero

### Layout
Full-width, altura minima 100vh. Fondo con gradiente sutil de blanco a verde muy claro (green-50). A la izquierda el texto, a la derecha una ilustracion/mockup del dashboard con el mapa de CDMX. En movil, el texto va arriba y la imagen abajo.

### Contenido

**Badge superior (chip pequeno arriba del titulo):**
```
Track IBM -- Ciudades Resilientes | Hackathon Genius Arena 2026
```

**Titulo principal (h1):**
```
La Ciudad de Mexico genera 12,700 toneladas de basura al dia.
El sistema para recogerla no ha cambiado en decadas.
```

**Subtitulo (p):**
```
EcoRuta usa sensores IoT, inteligencia artificial y optimizacion de rutas en tiempo real para transformar la recoleccion de residuos: menos kilometros, menos emisiones, mejor servicio.
```

**CTAs (dos botones lado a lado):**
- Boton primario (gradiente verde): `Ver demo en vivo` -> enlace al dashboard /admin/dashboard
- Boton secundario (outline verde): `Conocer la solucion` -> scroll a seccion de solucion

**Dato de impacto debajo de los CTAs (texto pequeno):**
```
25% menos km recorridos | 129 kg CO2 evitados por dia | < 5 segundos para generar una ruta
```

### Visual
- Lado derecho: screenshot/mockup del dashboard mostrando el mapa de CDMX con los puntos de contenedores (rojo, amarillo, verde) y las metricas. Puede ser una imagen estatica con borde redondeado y sombra sutil, ligeramente rotada para dar profundidad.
- Elementos decorativos: circulos verdes translucidos en el fondo (CSS, no imagenes) para dar dinamismo.

---

## Seccion 2: Problema

### Layout
Fondo blanco. Titulo centrado arriba. Debajo, una cuadricula de 3 columnas (1 columna en movil) con las tarjetas de datos. Despues, un parrafo de contexto.

### Contenido

**Titulo de seccion (h2):**
```
Un sistema de recoleccion disenado para otra epoca
```

**Subtitulo:**
```
Las rutas se planifican con semanas de anticipacion, sin datos reales. Los camiones recorren rutas completas aunque los contenedores esten al 30% de capacidad.
```

**Tarjetas de datos (3 cards):**

Tarjeta 1:
- Icono: icono de basura/contenedor (outline verde)
- Numero grande: `12,700 ton`
- Etiqueta: `de basura generada al dia en CDMX`
- Fuente: `SEDEMA`

Tarjeta 2:
- Icono: icono de dinero/billete
- Numero grande: `$500 MDP`
- Etiqueta: `invertidos en vehiculos e infraestructura (2025-2026)`
- Fuente: `Expansion`

Tarjeta 3:
- Icono: icono de ruta/mapa con X
- Numero grande: `0 datos`
- Etiqueta: `en tiempo real sobre el estado de los contenedores`
- Fuente: `INECC`

**Parrafo de cierre de seccion:**
```
El resultado: costos innecesarios, emisiones evitables, contenedores desbordados y ciudadanos insatisfechos. Mientras el transporte de personas ya se transformo con Uber, Waze y Google Maps, la recoleccion de basura sigue operando con rutas fijas y horarios rigidos.
```

### Visual
- Las tarjetas tienen fondo blanco, borde eco-border, sombra sutil, icono arriba en verde.
- Numero grande en texto eco-text-primary con font-bold.
- Debajo del parrafo de cierre: una linea visual tipo "antes vs despues" con dos columnas simples.

**Tabla visual "Antes vs Despues" (2 columnas):**

| Hoy | Con EcoRuta |
|-----|-------------|
| Rutas fijas y estaticas | Rutas dinamicas en tiempo real |
| Sin informacion de contenedores | Datos continuos via IoT |
| Decisiones manuales por intuicion | Decisiones automatizadas con IA |
| Impacto ambiental no medido | Reduccion medible de CO2 y combustible |

- Columna izquierda con fondo rojo muy suave (red-50), columna derecha con fondo verde muy suave (green-50).

---

## Seccion 3: Solucion

### Layout
Fondo verde muy claro (green-50/30). Titulo centrado. Debajo, una cuadricula de 4 tarjetas en 2x2 (o 4x1 en desktop, 1x4 en movil). Cada tarjeta tiene icono, titulo y descripcion.

### Contenido

**Titulo de seccion (h2):**
```
EcoRuta: recoleccion inteligente para ciudades que se anticipan
```

**Subtitulo:**
```
Un sistema que integra datos en tiempo real, inteligencia artificial y optimizacion matematica para que cada camion vaya solo donde se necesita.
```

**Tarjeta 1 -- Sensores IoT:**
- Icono: sensor/wifi (outline)
- Titulo: `Monitoreo en tiempo real`
- Texto: `Sensores IoT en cada contenedor transmiten niveles de ocupacion cada 10 segundos. Sabemos exactamente que contenedores necesitan atencion.`

**Tarjeta 2 -- Prediccion IA:**
- Icono: cerebro/red neuronal (outline)
- Titulo: `Prediccion con IA`
- Texto: `Modelos de machine learning predicen que contenedores estaran llenos en las proximas 24 horas, anticipando problemas antes de que ocurran.`

**Tarjeta 3 -- Rutas Optimizadas:**
- Icono: ruta/grafo (outline)
- Titulo: `Rutas optimizadas`
- Texto: `Algoritmos de optimizacion combinatoria (TSP + OR-Tools) generan la ruta mas eficiente en menos de 5 segundos, priorizando contenedores criticos.`

**Tarjeta 4 -- Comunicacion Natural:**
- Icono: chat/mensaje (outline)
- Titulo: `Instrucciones en lenguaje natural`
- Texto: `IBM Watsonx convierte datos tecnicos en instrucciones claras para conductores, reportes para gestores y alertas para ciudadanos. Sin formacion tecnica requerida.`

### Visual
- Tarjetas blancas con borde, icono grande en verde arriba (48x48px area), titulo en semi-bold, texto en secondary.
- Hover: sombra mas pronunciada y ligero translateY(-2px), como en auth-button.

---

## Seccion 4: Metricas de Impacto

### Layout
Fondo blanco. Titulo centrado. Cuadricula de 4 metricas en una fila horizontal (2x2 en movil). Despues, una nota sobre el escenario de calculo.

### Contenido

**Titulo de seccion (h2):**
```
Impacto medible desde el primer dia
```

**Subtitulo:**
```
Resultados estimados con una flota de 20 camiones en 3 zonas de la CDMX.
```

**Metrica 1:**
- Numero: `25%`
- Etiqueta: `menos kilometros recorridos`
- Detalle: `120 km/dia evitados vs ruta estandar`
- Color del numero: eco-green

**Metrica 2:**
- Numero: `129 kg`
- Etiqueta: `de CO2 evitados por dia`
- Detalle: `Equivalente a 2,350 arboles por ano`
- Color del numero: eco-green

**Metrica 3:**
- Numero: `$432K`
- Etiqueta: `MXN de ahorro anual en combustible`
- Detalle: `48 litros de diesel ahorrados al dia`
- Color del numero: eco-green

**Metrica 4:**
- Numero: `< 5s`
- Etiqueta: `para generar una ruta optimizada`
- Detalle: `2s optimizacion + 3s instrucciones IA`
- Color del numero: eco-green

**Nota al pie (texto pequeno, centrado):**
```
Escenario base: 20 camiones, 3 zonas, 50% de ocupacion promedio. Fuentes: SEDEMA, INECC, calculos propios con factor de emision 2.68 kg CO2/litro diesel (EPA).
```

### Visual
- Numeros en texto 4xl o 5xl, bold, color eco-green.
- Etiqueta en texto sm, secondary.
- Detalle en texto xs, secondary.
- Cada metrica centrada en su celda, con un icono sutil arriba del numero (flecha hacia abajo para km, hoja para CO2, moneda para ahorro, reloj para tiempo).

---

## Seccion 5: Como funciona

### Layout
Fondo verde muy claro (green-50/30). Titulo centrado. Dos sub-secciones: una para el flujo del sistema (tecnico) y otra dividida en dos columnas para el flujo del ciudadano y el flujo del municipio.

### Contenido

**Titulo de seccion (h2):**
```
Como funciona EcoRuta
```

**Sub-seccion A: Flujo del sistema (horizontal, con flechas)**

4 pasos en linea horizontal (vertical en movil), conectados por flechas o lineas:

Paso 1:
- Icono: sensor/antena
- Titulo: `Captura`
- Texto: `Sensores IoT y reportes ciudadanos alimentan datos continuos de cada contenedor.`

Paso 2:
- Icono: nube
- Titulo: `Procesamiento`
- Texto: `IBM Watsonx y PostgreSQL con PostGIS procesan y almacenan datos geoespaciales en la nube.`

Paso 3:
- Icono: cerebro/engranaje
- Titulo: `Optimizacion`
- Texto: `El motor de IA calcula rutas optimas y predice llenado futuro con machine learning.`

Paso 4:
- Icono: pantalla/app
- Titulo: `Accion`
- Texto: `Conductores reciben instrucciones claras. Gestores ven metricas en el dashboard. Ciudadanos reciben alertas.`

**Sub-seccion B: Dos flujos paralelos**

Columna izquierda -- "Para el ciudadano":
1. `Descarga la app (PWA, sin app store)`
2. `Reporta contenedores desbordados o anomalias desde su celular`
3. `Recibe notificaciones sobre el servicio en su colonia`

Columna derecha -- "Para el municipio":
1. `Los sensores detectan contenedores criticos automaticamente`
2. `El sistema genera rutas optimizadas y las asigna a conductores`
3. `Al final del turno, se genera un reporte de eficiencia automatico`

### Visual
- Flujo del sistema: tarjetas numeradas (1-4) con linea conectora punteada horizontal. Cada tarjeta tiene icono circular verde arriba.
- Flujos paralelos: dos cards lado a lado, cada una con lista numerada con circulos verdes. Card izquierda borde azul sutil (ciudadano), card derecha borde verde (municipio).

---

## Seccion 6: Arquitectura Tecnologica

### Layout
Fondo blanco. Titulo centrado. Diagrama visual de 4 capas apiladas (de abajo hacia arriba). Debajo, una fila con logos/badges de las tecnologias principales.

### Contenido

**Titulo de seccion (h2):**
```
Arquitectura de 4 capas
```

**Subtitulo:**
```
Cada capa opera de forma independiente. Si una falla, las demas siguen funcionando.
```

**Diagrama de capas (de abajo hacia arriba):**

Capa 1 (abajo, fondo verde-50):
- Label: `Captura de datos`
- Contenido: `Sensores IoT (50 contenedores, 3 zonas) + Reportes ciudadanos (app movil) + Datos historicos`

Capa 2:
- Label: `Procesamiento en la nube`
- Contenido: `FastAPI + PostgreSQL/PostGIS + IBM Cloud`

Capa 3:
- Label: `IA + Optimizacion`
- Contenido: `OR-Tools (TSP) + MLPRegressor (prediccion) + IBM Watsonx (lenguaje natural)`

Capa 4 (arriba, fondo verde):
- Label: `Presentacion`
- Contenido: `Dashboard operativo + App del conductor (PWA) + App ciudadana`

**Fila de tecnologias (badges horizontales):**
Cada badge es un rectangulo redondeado con nombre de la tecnologia:
- `Astro 6` `Tailwind 4` `FastAPI` `PostgreSQL + PostGIS` `IBM Watsonx` `OR-Tools` `scikit-learn` `Docker` `Cloudflare Pages`

### Visual
- Las capas se apilan visualmente como bloques, con la mas ancha abajo y la mas angosta arriba (o todas iguales).
- Flechas verticales entre capas indicando flujo de datos.
- Las capas usan tonos progresivos de verde (mas claro abajo, mas intenso arriba).
- Los badges de tecnologias son rectangulos pequenos con fondo gris claro, texto small, separados por un espacio.

---

## Seccion 7: Mercado y Oportunidad

### Layout
Fondo verde-50/30. Titulo centrado. Dos columnas: izquierda con datos de mercado, derecha con el diferenciador competitivo.

### Contenido

**Titulo de seccion (h2):**
```
Una oportunidad de mercado en el momento justo
```

**Columna izquierda -- Contexto de mercado:**

```
El mercado global de smart waste management esta valorado en USD 3.1 mil millones (2025) con crecimiento anual del 20%.
```

Tres datos en mini-cards:
- `16 alcaldias en CDMX, cada una con necesidades de optimizacion`
- `Separacion obligatoria de residuos desde enero 2026 -- nueva regulacion`
- `Nueva agencia de gestion de residuos en creacion -- ventana de oportunidad`

```
Mexico aun no tiene adopcion significativa de smart waste management. EcoRuta llega como primer movimiento en el mercado mexicano.
```

**Columna derecha -- Diferenciador:**

Titulo: `Por que EcoRuta es diferente`

Lista con checks verdes:
- `IA Generativa como interfaz humana -- ningun competidor lo tiene`
- `Sin hardware propietario -- funciona con cualquier sensor IoT estandar`
- `Disenado para el contexto mexicano -- espanol nativo, estructura de alcaldias, regulacion local`
- `Triple fuente de datos -- sensores + reportes ciudadanos + datos historicos`
- `Costo de entrada bajo -- modelo SaaS, sin inversion en contenedores de $4,000 USD`

### Visual
- Columna izquierda: texto con mini-cards con icono de check o flecha.
- Columna derecha: lista con iconos de check verde, fondo blanco, borde verde sutil, sombra suave.

---

## Seccion 8: Alineacion con ODS

### Layout
Fondo blanco. Titulo centrado. Fila de 3 tarjetas ODS principales, luego 2 secundarias mas pequenas debajo.

### Contenido

**Titulo de seccion (h2):**
```
Tecnologia con proposito social
```

**Subtitulo:**
```
EcoRuta contribuye directamente a los Objetivos de Desarrollo Sostenible de la ONU.
```

**ODS Principal 1:**
- Numero: `ODS 11`
- Nombre: `Ciudades y Comunidades Sostenibles`
- Descripcion: `Infraestructura inteligente para gestion de residuos urbanos. Mejor servicio publico para todos.`

**ODS Principal 2:**
- Numero: `ODS 13`
- Nombre: `Accion por el Clima`
- Descripcion: `Reduccion directa de emisiones de CO2: 129 kg diarios, equivalentes a 47 toneladas anuales.`

**ODS Principal 3:**
- Numero: `ODS 12`
- Nombre: `Produccion y Consumo Responsables`
- Descripcion: `Datos para decisiones informadas sobre generacion y recoleccion de residuos.`

**ODS Secundarios (mas pequenos):**
- `ODS 9 -- Industria, Innovacion e Infraestructura`
- `ODS 3 -- Salud y Bienestar`

### Visual
- Tarjetas con el numero ODS grande a la izquierda (circulo con fondo verde), nombre en bold, descripcion debajo.
- Los ODS secundarios son mas compactos, en linea horizontal.

---

## Seccion 9: Equipo

### Layout
Fondo verde-50/30. Titulo centrado. Cuadricula de 5 tarjetas de equipo (3+2 o 5 en fila en desktop, 2+2+1 en tablet, 1 en movil).

### Contenido

**Titulo de seccion (h2):**
```
El equipo detras de EcoRuta
```

**Subtitulo:**
```
Syle Studio -- 5 perfiles complementarios unidos por la mision de hacer ciudades mas inteligentes.
```

**Miembro 1:**
- Nombre: `Daniel Capistran Morales`
- Rol: `Backend / Cloud`
- Responsabilidad: `Arquitectura, integracion Watsonx, API`

**Miembro 2:**
- Nombre: `Pamela Mota Orozco`
- Rol: `Frontend / UX`
- Responsabilidad: `Dashboard operativo, prototipo de app`

**Miembro 3:**
- Nombre: `Diana Valeria Legorreta`
- Rol: `Datos / IA`
- Responsabilidad: `Simulador IoT, modelos de prediccion`

**Miembro 4:**
- Nombre: `Sandoval Vargas Luis Antonio`
- Rol: `QA / Integracion`
- Responsabilidad: `Pruebas, documentacion tecnica`

**Miembro 5:**
- Nombre: `Alcerreca Saldivar Karla Paola`
- Rol: `Pitch`
- Responsabilidad: `Narrativa del proyecto, presentacion`

### Visual
- Tarjetas blancas con avatar placeholder (circulo con iniciales y fondo verde aleatorio), nombre en bold, rol en badge verde, responsabilidad en texto secondary.
- Sin fotos reales (se pueden agregar despues).

---

## Seccion 10: CTA Final / Cierre

### Layout
Full-width. Fondo con gradiente verde (de eco-green a eco-green-dark). Texto blanco centrado. Gran CTA.

### Contenido

**Titulo (h2, blanco):**
```
Convertir la recoleccion de basura de un servicio reactivo y costoso en un sistema inteligente, predictivo y medible.
```

**Subtitulo (blanco, translucido):**
```
EcoRuta es la primera solucion pensada desde Mexico, para Mexico, con tecnologia IBM de clase mundial.
```

**CTA (boton blanco con texto verde):**
```
Ver demo en vivo
```

**Datos finales (tres metricas en linea, texto blanco):**
- `12,700 ton/dia de basura en CDMX`
- `$500 MDP invertidos en infraestructura`
- `0 sistemas inteligentes desplegados -- hasta ahora`

### Visual
- Gradiente verde oscuro a verde medio.
- Texto blanco grande, centrado.
- Boton blanco con texto verde, sombra verde translucida.
- Efecto decorativo: circulos translucidos blancos en el fondo (CSS).

---

## Seccion 11: Footer

### Layout
Fondo oscuro (#111827 o eco-text-primary). Texto claro. Simple.

### Contenido

```
EcoRuta -- Sistema de Gestion de Residuos con Rutas Dinamicas
Track IBM Ciudades Resilientes | Hackathon Genius Arena 2026
Syle Studio | 2026
```

Links opcionales:
- GitHub del proyecto
- Documentacion API (/docs)

### Visual
- Minimalista. Logo pequeno + texto. Una linea horizontal separadora.

---

## Notas de implementacion

### Animaciones sugeridas
- Hero: fade-in del texto desde abajo (0.5s delay escalonado titulo -> subtitulo -> CTAs)
- Metricas de impacto: contador animado (count up) cuando la seccion entra en viewport (Intersection Observer)
- Tarjetas de solucion: fade-in escalonado al hacer scroll
- Flujo "como funciona": las flechas conectoras se dibujan progresivamente al hacer scroll

### SEO y Meta
- Title: `EcoRuta -- Recoleccion Inteligente de Residuos para CDMX`
- Description: `Sistema de gestion de residuos con IoT, IA y rutas dinamicas. Reduce 25% de km recorridos y 129 kg de CO2 diarios.`
- OG Image: screenshot del dashboard con el mapa

### Performance
- La landing page debe ser totalmente estatica (SSG con Astro), sin JavaScript necesario excepto para animaciones opcionales y el contador.
- Imagenes en formato WebP, lazy loaded.
- No depender de la API del backend para ningun dato de la landing -- todos los numeros son hardcoded del research.

### Ruta
- La landing page reemplaza el contenido actual de `/` (index.astro).
- El dashboard se mantiene en `/admin/dashboard`.
- Agregar link en el navbar de la landing hacia el login y el dashboard.

---

## Resumen de datos clave para copiar al implementar

| Dato | Valor | Fuente |
|------|-------|--------|
| Basura diaria CDMX | 12,700 toneladas | SEDEMA |
| Inversion gobierno 2025-2026 | $500 MDP | Expansion |
| Reduccion de km estimada | >= 25% | Calculo propio (50 contenedores) |
| CO2 evitado por dia | ~129 kg | Factor 2.68 kg/litro diesel (EPA) |
| CO2 evitado por ano | ~47 toneladas | Proyeccion |
| Equivalente en arboles | ~2,350 arboles/ano | EPA calculator |
| Ahorro en combustible | 18-25% | Calculo propio |
| Ahorro anual MXN (1 alcaldia) | ~$432,000 | 48 litros/dia x $25/litro x 360 dias |
| Tiempo de generacion de ruta | < 5 segundos | 2s optimizacion + 3s IA |
| Contenedores en MVP | 50 | 3 zonas CDMX |
| Mercado global smart waste | USD 3.1B (2025) | Technavio, 360iResearch |
| CAGR del mercado | ~20% | Technavio |
| Camiones recolectores CDMX | ~2,500 | SEDEMA |
| Alcaldias en CDMX | 16 | -- |
| Separacion obligatoria | Enero 2026 | Gobierno CDMX |
| Escala a toda CDMX: CO2/dia | ~16,125 kg | Proyeccion |
| Escala a toda CDMX: CO2/ano | ~5,885 toneladas | Proyeccion |
