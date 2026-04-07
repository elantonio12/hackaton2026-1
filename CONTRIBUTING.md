# Como contribuir

## Requisitos

- Git instalado
- Python 3.12 (opcional, para correr local)

## Flujo de trabajo

1. Clona el repo:
   ```bash
   git clone https://github.com/sylestudio/hackaton2026.git
   cd hackaton2026
   ```

2. Crea tu rama:
   ```bash
   git checkout -b mi-feature
   ```

3. Haz tus cambios y sube:
   ```bash
   git add .
   git commit -m "Descripcion de lo que hiciste"
   git push origin mi-feature
   ```

4. Abre un Pull Request en GitHub hacia `main`.

5. Espera la revision y aprobacion.

## Estructura del proyecto

```
hackaton2026/
├── backend/       ← API en FastAPI (Python)
├── frontend/      ← Dashboard (React)
├── simulator/     ← Simulador de sensores IoT
├── docker-compose.yml
└── .github/workflows/  ← CI/CD automatico
```

## Reglas

- **Nunca hagas push directo a `main`**, siempre usa Pull Request.
- Escribe mensajes de commit claros.
- Si algo no funciona, abre un Issue.
