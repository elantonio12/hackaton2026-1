# Participación de Sylestudio en el hackaton Genius Area

## EcoRuta - Sistema de Gestión de Residuos con Rutas Dinámicas

Track IBM - Ciudades Resilientes | IA Generativa para Ciudades Inteligentes y Sostenibles

### Estructura del proyecto

```
hackaton2026/
├── backend/          # API FastAPI + Motor de rutas + Watsonx
├── frontend/         # Dashboard operativo con mapa interactivo
├── simulator/        # Simulador de sensores IoT (50 contenedores, 3 zonas CDMX)
├── docker-compose.yml
└── .github/workflows/  # CI/CD automatico
```

### Levantar el proyecto

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs

### Equipo

| Integrante | Rol |
|---|---|
| Daniel Capistran Morales | Backend / Cloud |
| Pamela Mota Orozco | Frontend / UX |
| Diana Valeria Legorreta | Datos / IA |
| Sandoval Vargas Luis Antonio | QA / Integracion |
| Alcerreca Saldivar Karla Paola | Pitch |
