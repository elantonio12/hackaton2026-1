from app.core.config import settings
from app.models.schemas import OptimizedRoute


def generate_driver_instructions(route: OptimizedRoute) -> str:
    """Use IBM Watsonx to generate natural language instructions for a driver."""
    # TODO: Integrate with IBM Watsonx API
    # For now, return a template-based response as fallback
    stops_text = "\n".join(
        f"  {s.order}. Contenedor {s.container_id} (llenado: {s.fill_level:.0%})"
        for s in route.stops
    )
    return (
        f"Ruta para {route.vehicle_id}:\n"
        f"Total de paradas: {route.containers_visited}\n"
        f"Distancia estimada: {route.total_distance_km} km\n"
        f"Tiempo estimado: {route.estimated_time_min} min\n\n"
        f"Secuencia de recolección:\n{stops_text}"
    )


def generate_executive_summary(routes: list[OptimizedRoute]) -> str:
    """Generate an executive summary for the municipal manager."""
    # TODO: Integrate with IBM Watsonx API
    total_km = sum(r.total_distance_km for r in routes)
    total_containers = sum(r.containers_visited for r in routes)
    return (
        f"Resumen ejecutivo:\n"
        f"Vehículos desplegados: {len(routes)}\n"
        f"Contenedores atendidos: {total_containers}\n"
        f"Distancia total: {total_km:.1f} km\n"
    )
