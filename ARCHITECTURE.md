# Arquitectura del Sistema — EcoRuta

## Diagrama General

```mermaid
graph TB
    subgraph Users["Usuarios"]
        Admin["Admin"]
        Recolector["Recolector"]
        Ciudadano["Ciudadano"]
    end

    subgraph CloudflarePages["Cloudflare Pages (CDN)"]
        Frontend["Frontend<br/>Astro 6 + Tailwind 4<br/>PWA + Service Worker"]
    end

    subgraph VPS["VPS 69.6.202.19"]
        subgraph DockerCompose["Docker Compose"]
            Backend["FastAPI<br/>Uvicorn<br/>Python 3.12"]
            DB[("PostgreSQL 16<br/>+ PostGIS")]
            Simulator["Simulador IoT<br/>50 sensores<br/>cada 10s"]
        end
    end

    subgraph ExternalServices["Servicios Externos"]
        Watsonx["IBM Watsonx AI"]
        Resend["Resend Email"]
        GoogleOAuth["Google OAuth"]
    end

    Admin --> Frontend
    Recolector --> Frontend
    Ciudadano --> Frontend

    Frontend -- "HTTPS / JWT" --> Backend
    Backend -- "asyncpg" --> DB
    Simulator -- "POST /readings" --> Backend
    Backend -. "API Key" .-> Watsonx
    Backend -. "SMTP" .-> Resend
    Backend -. "OAuth 2.0" .-> GoogleOAuth
```

## Diagrama de Componentes del Backend

```mermaid
graph LR
    subgraph API["API Routes (/api/v1)"]
        Auth["/auth<br/>Login, Invite, Verify"]
        Containers["/containers<br/>Readings, Critical"]
        Routes["/routes<br/>Optimize"]
        Sensors["/sensors<br/>CRUD, Readings"]
        Predictions["/predictions<br/>Fill 24h, Retrain"]
        Collectors["/collectors<br/>CRUD"]
        Reports["/reports<br/>Citizen Reports"]
        Metrics["/metrics<br/>Efficiency, Coverage"]
        UserAPI["/user<br/>Truck ETA, Schedule"]
    end

    subgraph Services["Servicios de Negocio"]
        Optimizer["optimizer.py<br/>TSP Greedy<br/>Haversine"]
        PredictionSvc["prediction.py<br/>MLPRegressor<br/>Fill Prediction"]
        TruckPred["truck_prediction.py<br/>MLPRegressor<br/>ETA Prediction"]
        MetricsSvc["metrics.py<br/>Eficiencia, Costos"]
        WatsonxSvc["watsonx.py<br/>NLG Instructions"]
    end

    subgraph Data["Capa de Datos"]
        Models["SQLAlchemy Models"]
        Alembic["Alembic Migrations"]
        Database[("PostgreSQL<br/>+ PostGIS")]
    end

    Routes --> Optimizer
    Predictions --> PredictionSvc
    UserAPI --> TruckPred
    Metrics --> MetricsSvc
    Routes --> WatsonxSvc

    Auth --> Models
    Containers --> Models
    Sensors --> Models
    Collectors --> Models
    Reports --> Models

    Models --> Database
    Alembic --> Database
```

## Modelo de Datos

```mermaid
erDiagram
    users {
        uuid sub PK
        string email UK
        string name
        string role "admin | recolector | ciudadano"
        string provider "credentials | google"
        string password_hash
        timestamp created_at
        timestamp last_login
    }

    sensors {
        string sensor_id PK
        string container_id FK
        float latitude
        float longitude
        string zone "norte | centro | sur"
        string status "active | inactive"
    }

    container_readings {
        string container_id FK
        float fill_level "0.0 - 1.0"
        timestamp timestamp
        float latitude
        float longitude
        string zone
    }

    citizen_reports {
        int id PK
        float latitude
        float longitude
        text description
        string zone
        timestamp created_at
    }

    collectors {
        int id PK
        string nombre
        string empleado_id
        string zona
        string camion_id
        bool activo
        string telefono
    }

    problem_reports {
        int id PK
        string container_id FK
        string tipo_problema
        text descripcion
        string status
        timestamp timestamp
    }

    sensors ||--o{ container_readings : "genera"
    sensors ||--o{ problem_reports : "reporta"
```

## Flujo de Datos en Tiempo Real

```mermaid
sequenceDiagram
    participant Sim as Simulador IoT
    participant API as FastAPI
    participant DB as PostgreSQL
    participant ML as MLPRegressor
    participant UI as Frontend (PWA)

    loop Cada 10 segundos
        Sim->>API: POST /containers/readings
        API->>DB: INSERT container_reading
        API->>ML: Append to history
        alt Cada 50 readings
            ML->>ML: Auto-retrain model
        end
    end

    UI->>API: GET /containers/critical
    API->>DB: SELECT fill_level > 0.8
    API-->>UI: Contenedores criticos

    UI->>API: GET /predictions/{id}
    API->>ML: predict(features)
    ML-->>API: fill_level_24h
    API-->>UI: Prediccion

    UI->>API: POST /routes/optimize
    API->>API: TSP Greedy + Haversine
    API-->>UI: Ruta optimizada
```

## Infraestructura y Despliegue

```mermaid
graph TB
    subgraph GitHub["GitHub (sylestudio/hackaton2026)"]
        Repo["Repositorio"]
        Actions["GitHub Actions<br/>Self-hosted runner"]
        Secrets["Secrets<br/>JWT, API Keys, OAuth"]
    end

    subgraph DNS["Cloudflare DNS (syle.studio)"]
        FrontDNS["hackaton2026.syle.studio<br/>CNAME → pages.dev"]
        BackDNS["api.hackaton2026.syle.studio<br/>A → 69.6.202.19"]
    end

    subgraph CF["Cloudflare Pages"]
        FrontDeploy["Frontend Build<br/>Astro SSG"]
    end

    subgraph VPS["VPS (69.6.202.19:22022)"]
        Docker["Docker Compose"]
        Backend["backend:8000"]
        PostGIS["db:5432"]
        SimContainer["simulator"]
        Volume["pgdata volume"]
    end

    Repo -- "push frontend" --> CF
    Repo -- "push main" --> Actions
    Actions -- "docker compose up" --> Docker
    CF --> FrontDeploy

    FrontDNS --> FrontDeploy
    BackDNS --> Backend

    Docker --> Backend
    Docker --> PostGIS
    Docker --> SimContainer
    PostGIS --- Volume
```

## Stack Tecnologico

```mermaid
mindmap
  root((EcoRuta))
    Frontend
      Astro 6
      Tailwind CSS 4
      Vite PWA
      Service Worker
    Backend
      FastAPI
      SQLAlchemy 2.0 async
      Pydantic
      python-jose JWT
      bcrypt
    Base de Datos
      PostgreSQL 16
      PostGIS
      Alembic
    Machine Learning
      scikit-learn
      MLPRegressor
      Feature Engineering
    Optimizacion
      OR-Tools 9.12
      NetworkX
      Haversine
    Infraestructura
      Docker Compose
      GitHub Actions
      Cloudflare Pages
      Let s Encrypt
    Integraciones
      IBM Watsonx
      Resend Email
      Google OAuth
      SEDEMA Schedules
```
