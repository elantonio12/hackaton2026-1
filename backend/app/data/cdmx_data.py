"""CDMX alcaldía dataset and container distribution generator.

Mirror of simulator/cdmx_data.py. Both modules use the same data and
the same RNG seed (42), so the backend's seeded sensor registry and
the simulator's container set generate identical container_ids and
coordinates — no coordination needed.

Data sources:
- INEGI Census 2020 for population per alcaldía
- Wikipedia / INE for centroid coordinates and approximate area
"""

import math
import random
from dataclasses import dataclass


@dataclass
class Alcaldia:
    name: str         # normalized, lowercase, no spaces
    display: str      # human-readable name
    lat: float        # centroid latitude
    lon: float        # centroid longitude
    population: int   # INEGI Censo 2020
    area_km2: float   # approximate area


ALCALDIAS: list[Alcaldia] = [
    Alcaldia("iztapalapa", "Iztapalapa", 19.3574, -99.0667, 1835486, 117.5),
    Alcaldia("gustavo_a_madero", "Gustavo A. Madero", 19.4828, -99.1133, 1173351, 88.1),
    Alcaldia("alvaro_obregon", "Álvaro Obregón", 19.3587, -99.2039, 759137, 96.2),
    Alcaldia("tlalpan", "Tlalpan", 19.2926, -99.1707, 699928, 312.0),
    Alcaldia("coyoacan", "Coyoacán", 19.3467, -99.1617, 614447, 54.4),
    Alcaldia("cuauhtemoc", "Cuauhtémoc", 19.4326, -99.1472, 545884, 32.4),
    Alcaldia("xochimilco", "Xochimilco", 19.2574, -99.1035, 442178, 122.0),
    Alcaldia("venustiano_carranza", "Venustiano Carranza", 19.4342, -99.1056, 443704, 33.4),
    Alcaldia("benito_juarez", "Benito Juárez", 19.3744, -99.1569, 434153, 26.6),
    Alcaldia("azcapotzalco", "Azcapotzalco", 19.4872, -99.1852, 432205, 33.5),
    Alcaldia("miguel_hidalgo", "Miguel Hidalgo", 19.4280, -99.2064, 414470, 46.4),
    Alcaldia("iztacalco", "Iztacalco", 19.3962, -99.0973, 404695, 23.1),
    Alcaldia("tlahuac", "Tláhuac", 19.2819, -99.0072, 392313, 85.3),
    Alcaldia("la_magdalena_contreras", "La Magdalena Contreras", 19.3098, -99.2544, 247622, 74.6),
    Alcaldia("cuajimalpa_de_morelos", "Cuajimalpa de Morelos", 19.3589, -99.2930, 217686, 74.6),
    Alcaldia("milpa_alta", "Milpa Alta", 19.1936, -99.0238, 152685, 288.4),
]


def _radius_degrees(area_km2: float) -> float:
    radius_km = math.sqrt(area_km2 / math.pi)
    return radius_km / 111.0


def _distribute_counts(total: int) -> list[int]:
    total_pop = sum(a.population for a in ALCALDIAS)
    raw = [(a.population / total_pop) * total for a in ALCALDIAS]
    counts = [int(math.floor(r)) for r in raw]
    remainder = total - sum(counts)
    fractions = sorted(
        enumerate(r - math.floor(r) for r in raw),
        key=lambda x: x[1],
        reverse=True,
    )
    for i in range(remainder):
        counts[fractions[i % len(fractions)][0]] += 1
    return counts


def generate_containers(n: int, seed: int = 42) -> list[dict]:
    """Generate N container definitions across CDMX alcaldías.

    Uses the same deterministic RNG seed as the simulator, so a backend
    call to generate_containers(N) produces the exact same container_ids,
    coordinates, and zones as simulator/cdmx_data.py.
    """
    rng = random.Random(seed)
    counts = _distribute_counts(n)
    containers: list[dict] = []
    idx = 1
    for alcaldia, count in zip(ALCALDIAS, counts):
        sigma = _radius_degrees(alcaldia.area_km2) * 0.4
        for _ in range(count):
            lat = alcaldia.lat + rng.gauss(0, sigma)
            lon = alcaldia.lon + rng.gauss(0, sigma)
            containers.append({
                "id": f"CNT-{idx:05d}",
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "zone": alcaldia.name,
                "display_zone": alcaldia.display,
                "fill_level": round(rng.uniform(0.05, 0.65), 3),
            })
            idx += 1
    return containers
