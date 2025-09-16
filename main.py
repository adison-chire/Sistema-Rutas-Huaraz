import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import redis
import osmnx as ox
import networkx as nx
import os
from datetime import datetime, time, timedelta
import logging
import json
import copy

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuración de la Base de Datos y Redis ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "huaraz_rutas")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "alma94moroni")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

app = FastAPI(
    title="API de Rutas Inteligentes para Huaraz",
    description="API para calcular rutas óptimas y alternativas en Huaraz, considerando datos de tráfico y modelos de IA.",
    version="0.1.0"
)

# --- Modelos Pydantic para validación de entrada y salida ---
class Location(BaseModel):
    lat: float
    lon: float

class RouteRequest(BaseModel):
    origin: Location
    destination: Location

class RouteSegment(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    congestion_level: float
    tipo_via_osm: str = "N/A"
    categoria_congestion: str = "Desconocida"
    length_meters: float
    travel_time_seconds: float
    speed_kmh: float

class SingleRouteDetails(BaseModel):
    nodos_de_ruta: list[int]
    coordenadas_de_ruta: list[Location]
    segmentos_de_ruta: list[RouteSegment]
    tiempo_total_viaje_segundos: float
    tiempo_total_viaje_minutos: float
    total_distance_meters: float
    recomendacion_ruta: str
    overall_congestion: float
    overall_congestion_category: str

class MultiRouteResponse(BaseModel):
    mensaje: str
    nodo_origen_osmid: int
    nodo_destino_osmid: int
    rutas_alternativas: list[SingleRouteDetails]

# Variables globales para el grafo y las conexiones
G = None
db_pool = None
redis_client = None

def get_edge_travel_times(query_datetime: datetime) -> dict:
    """
    Obtiene los tiempos de viaje estimados y el nivel de congestión para cada arista.
    Primero intenta desde Redis. Si no encuentra o está vacío para la hora,
    lo obtiene de PostgreSQL y lo cachea en Redis.
    Retorna un diccionario con (u, v, key) -> {'travel_time': X, 'congestion_level': Y, ...}
    """
    logger.info(f"Obteniendo tiempos de viaje para: {query_datetime.strftime('%Y-%m-%d %H:%M:%S')}")

    day_of_week = query_datetime.weekday()
    hour_of_day = query_datetime.hour

    redis_key = f"traffic:{day_of_week}:{hour_of_day}"
    edge_data_from_db = {}

    try:
        redis_data = redis_client.hgetall(redis_key)

        if redis_data:
            logger.info(f"Datos de tráfico encontrados en Redis para {redis_key}. Cantidad: {len(redis_data)}")
            for edge_id_str, json_data_str in redis_data.items():
                u_str, v_str, key_str = edge_id_str.split('-')
                parsed_data = json.loads(json_data_str)
                edge_data_from_db[(int(u_str), int(v_str), int(key_str))] = {
                    'travel_time': parsed_data.get('travel_time', 0.0),
                    'congestion_level': parsed_data.get('congestion_level', 0.0),
                    'categoria_congestion': parsed_data.get('categoria_congestion', 'Desconocida'),
                    'tipo_via_osm': parsed_data.get('tipo_via_osm', 'N/A'),
                    'length': parsed_data.get('length', 0.0),
                    'speed_kmh': parsed_data.get('speed_kmh', 0.0)
                }
            return edge_data_from_db
        else:
            logger.info(f"No hay datos de tráfico en Redis para {redis_key}. Consultando PostgreSQL.")

    except redis.exceptions.ConnectionError as e:
        logger.warning(f"No se pudo conectar a Redis al obtener tráfico, consultando PostgreSQL. Error: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar JSON de Redis para {redis_key}: {e}. Consultando PostgreSQL.")
    except Exception as e:
        logger.error(f"Error inesperado al intentar obtener datos de Redis: {e}. Consultando PostgreSQL.")

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u, v, edge_key, tiempoviajeestimadosegundos, nivel_congestion,
                       categoria_congestion, tipo_via_osm, length, velocidad_promedio_kmh
                FROM datos_trafico
                WHERE dia_de_semana = %s AND hora_del_dia = %s;
                """,
                (day_of_week, hour_of_day)
            )
            for record in cur:
                edge_data_from_db[(record['u'], record['v'], record['edge_key'])] = {
                    'travel_time': record.get('tiempoviajeestimadosegundos', 0.0),
                    'congestion_level': record.get('nivel_congestion', 0.0),
                    'categoria_congestion': record.get('categoria_congestion', 'Desconocida'),
                    'tipo_via_osm': record.get('tipo_via_osm', 'N/A'),
                    'length': record.get('length', 0.0),
                    'speed_kmh': record.get('velocidad_promedio_kmh', 0.0)
                }
    except psycopg2.Error as e:
        logger.error(f"Error al conectar o consultar la base de datos para tiempos de tráfico: {e}")
        raise HTTPException(status_code=500, detail=f"Error en DB al obtener tráfico: {e}")
    except Exception as e:
        logger.error(f"Error inesperado al obtener tiempos de tráfico (desde PG o al cachear): {e}")
        raise HTTPException(status_code=500, detail=f"Error inesperado al obtener tráfico: {e}")
    finally:
        if conn:
            db_pool.putconn(conn)

    logger.info(f"Se encontraron {len(edge_data_from_db)} tiempos de viaje y congestión en PostgreSQL para el día {day_of_week} hora {hour_of_day}.")

    if edge_data_from_db and redis_client:
        # Eliminar la clave antigua antes de insertar nuevos datos para asegurar frescura
        redis_client.delete(redis_key)
        redis_hash_data = {
            f"{u}-{v}-{key}": json.dumps(data)
            for (u, v, key), data in edge_data_from_db.items()
        }
        redis_client.hmset(redis_key, redis_hash_data)
        logger.info(f"Datos de tráfico para {redis_key} cacheados en Redis.")

    return edge_data_from_db


async def refresh_traffic_data_in_redis():
    """
    Tarea en segundo plano para refrescar los datos de tráfico en Redis periódicamente.
    """
    global redis_client, db_pool

    REFRESH_INTERVAL_SECONDS = 900 # 15 minutos

    while True:
        logger.info("Iniciando ciclo completo de refresco de datos de tráfico en Redis para futuras horas/días...")

        hours_to_cache = 24
        days_to_cache = 2

        now = datetime.now()

        for day_offset in range(days_to_cache):
            for hour_offset in range(hours_to_cache):
                target_datetime = now + timedelta(days=day_offset, hours=hour_offset)

                target_day_of_week = target_datetime.weekday()
                target_hour_of_day = target_datetime.hour

                redis_key = f"traffic:{target_day_of_week}:{target_hour_of_day}"

                conn = None
                try:
                    conn = db_pool.getconn()
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(
                            """
                            SELECT u, v, edge_key, tiempoviajeestimadosegundos, nivel_congestion,
                                   categoria_congestion, tipo_via_osm, length, velocidad_promedio_kmh
                            FROM datos_trafico
                            WHERE dia_de_semana = %s AND hora_del_dia = %s;
                            """,
                            (target_day_of_week, target_hour_of_day)
                        )
                        pg_data = {}
                        for record in cur:
                            pg_data[(record['u'], record['v'], record['edge_key'])] = {
                                'travel_time': record.get('tiempoviajeestimadosegundos', 0.0),
                                'congestion_level': record.get('nivel_congestion', 0.0),
                                'categoria_congestion': record.get('categoria_congestion', 'Desconocida'),
                                'tipo_via_osm': record.get('tipo_via_osm', 'N/A'),
                                'length': record.get('length', 0.0),
                                'speed_kmh': record.get('velocidad_promedio_kmh', 0.0)
                            }
                    
                    if pg_data and redis_client:
                        # Eliminar la clave antigua antes de insertar nuevos datos para asegurar frescura
                        redis_client.delete(redis_key) 
                        redis_hash_data = {
                            f"{u}-{v}-{key}": json.dumps(data)
                            for (u, v, key), data in pg_data.items()
                        }
                        redis_client.hmset(redis_key, redis_hash_data)

                        expiration_seconds = 3600 + REFRESH_INTERVAL_SECONDS
                        redis_client.expire(redis_key, expiration_seconds)
                        logger.info(f"Datos de tráfico para {redis_key} (Día: {target_day_of_week}, Hora: {target_hour_of_day}) actualizados y establecidos para expirar en {expiration_seconds}s.")
                    else:
                        logger.warning(f"No se encontraron datos de tráfico en PostgreSQL para el día {target_day_of_week} hora {target_hour_of_day} o Redis no está disponible.")

                except redis.exceptions.ConnectionError as e:
                    logger.error(f"Error de conexión a Redis durante el refresco de datos: {e}")
                except psycopg2.Error as e:
                    logger.error(f"Error de DB al obtener datos para refresco de Redis para {redis_key}: {e}")
                except Exception as e:
                    logger.error(f"Error inesperado durante el refresco de Redis para {redis_key}: {e}")
                finally:
                    if conn:
                        db_pool.putconn(conn)
                
                await asyncio.sleep(0.05) # Pequeña pausa para evitar saturar el pool de conexiones

        logger.info(f"Ciclo completo de refresco de Redis terminado. Esperando {REFRESH_INTERVAL_SECONDS}s para el próximo ciclo.")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    global G, db_pool, redis_client
    logger.info("Iniciando la aplicación FastAPI...")
    try:
        graph_path = "calles_huaraz.graphml"
        if os.path.exists(graph_path):
            G = ox.load_graphml(graph_path)
            logger.info(f"Grafo de Huaraz cargado en memoria. Nodos: {len(G.nodes)}, Aristas: {len(G.edges)}")
        else:
            logger.error(f"Archivo de grafo no encontrado en: {graph_path}")
            raise FileNotFoundError(f"El archivo {graph_path} no se encontró. Asegúrate de que el grafo de Huaraz esté en la raíz del proyecto.")

        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=50, # Aumentado el tamaño del pool de conexiones
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_pool.putconn(conn)
        logger.info("Conexión exitosa a PostgreSQL.")

        redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        redis_client.ping()
        logger.info("Conexión exitosa a Redis.")

        logger.info("Aplicación FastAPI iniciada y conexiones verificadas.")
        asyncio.create_task(refresh_traffic_data_in_redis())
        logger.info("Tarea de refresco de datos de tráfico en Redis iniciada en segundo plano.")

    except Exception as e:
        logger.error(f"Error durante el inicio de la aplicación: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Pool de conexiones a PostgreSQL cerrado.")
    if redis_client:
        redis_client.close()
        logger.info("Conexión a Redis cerrada.")
    logger.info("Aplicación FastAPI apagada.")

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

def get_route_details(graph, route_nodes):
    """
    Extrae los detalles de una ruta específica, incluyendo segmentos, congestión y distancia.
    Se itera manualmente sobre las aristas de la ruta para obtener sus atributos.
    """
    route_coordinates = []
    route_segments_data = []
    total_congestion_sum = 0.0
    num_segments = 0
    total_distance_meters = 0.0
    total_travel_time_seconds = 0.0

    def get_overall_congestion_category(overall_congestion_level):
        if overall_congestion_level < 0.3:
            return "Baja"
        elif overall_congestion_level < 0.7 and overall_congestion_level >= 0.3:
            return "Media"
        else:
            return "Alta"
        
    if route_nodes:
        route_coordinates.append({"lat": graph.nodes[route_nodes[0]]['y'], "lon": graph.nodes[route_nodes[0]]['x']})

    for i in range(len(route_nodes) - 1):
        u_node = route_nodes[i]
        v_node = route_nodes[i+1]

        start_lat = graph.nodes[u_node]['y']
        start_lon = graph.nodes[u_node]['x']
        end_lat = graph.nodes[v_node]['y']
        end_lon = graph.nodes[v_node]['x']

        # Añadir la coordenada del nodo final del segmento.
        if i < len(route_nodes) - 2:
            route_coordinates.append({"lat": end_lat, "lon": end_lon})

        chosen_edge_data = None
        if graph.has_edge(u_node, v_node):
            for key_in_multigraph in graph[u_node][v_node]:
                current_edge_attrs = graph[u_node][v_node][key_in_multigraph]
                if 'travel_time' in current_edge_attrs:
                    chosen_edge_data = current_edge_attrs
                    break

        if chosen_edge_data:
            congestion_level = chosen_edge_data.get('congestion_level', 0.0)
            edge_length = chosen_edge_data.get('length', 0.0)
            travel_time_segment = chosen_edge_data.get('travel_time', 0.0)
            tipo_via_osm = chosen_edge_data.get('tipo_via_osm', 'N/A')
            categoria_congestion_segment = chosen_edge_data.get('categoria_congestion', 'Desconocida')
            speed_kmh_segment = chosen_edge_data.get('speed_kmh', 0.0)

            route_segments_data.append({
                "start_lat": start_lat,
                "start_lon": start_lon,
                "end_lat": end_lat,
                "end_lon": end_lon,
                "congestion_level": congestion_level,
                "tipo_via_osm": tipo_via_osm,
                "categoria_congestion": categoria_congestion_segment,
                "length_meters": edge_length,
                "travel_time_seconds": travel_time_segment,
                "speed_kmh": speed_kmh_segment
            })
            total_congestion_sum += congestion_level
            num_segments += 1
            total_distance_meters += edge_length
            total_travel_time_seconds += travel_time_segment
        else:
            logger.warning(f"No se encontraron datos de tráfico para la arista ({u_node}, {v_node}) en get_route_details. Usando valores por defecto.")
            route_segments_data.append({
                "start_lat": start_lat,
                "start_lon": start_lon,
                "end_lat": end_lat,
                "end_lon": end_lon,
                "congestion_level": 0.0,
                "tipo_via_osm": "Desconocido",
                "categoria_congestion": "Desconocida",
                "length_meters": graph[u_node][v_node][0].get('length', 0.0) if graph.has_edge(u_node, v_node) else 0.0,
                "travel_time_seconds": 0.0,
                "speed_kmh": 0.0
            })

    if route_nodes and len(route_coordinates) < len(route_nodes):
        last_node = route_nodes[-1]
        route_coordinates.append({"lat": graph.nodes[last_node]['y'], "lon": graph.nodes[last_node]['x']})

    overall_congestion = total_congestion_sum / num_segments if num_segments > 0 else 0.0
    overall_congestion_category = get_overall_congestion_category(overall_congestion)

    if overall_congestion >= 0.7:
        recomendacion = "Ruta muy congestionada"
    elif overall_congestion >= 0.4:
        recomendacion = "Ruta con congestión media"
    else:
        recomendacion = "Ruta óptima / poco congestionada"

    return SingleRouteDetails(
        nodos_de_ruta=route_nodes,
        coordenadas_de_ruta=route_coordinates,
        segmentos_de_ruta=route_segments_data,
        tiempo_total_viaje_segundos=round(total_travel_time_seconds, 2),
        tiempo_total_viaje_minutos=round(total_travel_time_seconds / 60, 2),
        total_distance_meters=round(total_distance_meters, 2),
        recomendacion_ruta=recomendacion,
        overall_congestion=overall_congestion,
        overall_congestion_category=overall_congestion_category
    )

@app.post("/calculate_route", response_model=MultiRouteResponse)
async def calculate_route(request: RouteRequest):
    logger.info(f"Solicitud de ruta recibida: Origen({request.origin.lat}, {request.origin.lon}), Destino({request.destination.lat}, {request.destination.lon})")

    if G is None:
        raise HTTPException(status_code=500, detail="Grafo no cargado. Error de inicialización del servidor.")

    orig_node = ox.nearest_nodes(G, request.origin.lon, request.origin.lat)
    dest_node = ox.nearest_nodes(G, request.destination.lon, request.destination.lat)

    logger.info(f"Nodos OSMnx encontrados: Origen {orig_node}, Destino {dest_node}")

    current_time = datetime.now()
    try:
        edge_data_from_db = get_edge_travel_times(current_time)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error al obtener tiempos de viaje: {e}")
        raise HTTPException(status_code=500, detail=f"Error inesperado al obtener tráfico: {e}")

    DEFAULT_SPEED_MPS = 20 * 1000 / 3600 # 20 km/h en m/s

    G_with_traffic_weights = copy.deepcopy(G)

    for u, v, key, data in G_with_traffic_weights.edges(keys=True, data=True):
        edge_id = (u, v, key)
        if edge_id in edge_data_from_db:
            for attr_name, attr_value in edge_data_from_db[edge_id].items():
                G_with_traffic_weights[u][v][key][attr_name] = attr_value
        else:
            length_meters = data.get('length', 1)
            default_speed_kmh = data.get('maxspeed', 20)
            if isinstance(default_speed_kmh, list):
                default_speed_kmh = float(default_speed_kmh[0]) if default_speed_kmh else 20
            else:
                default_speed_kmh = float(default_speed_kmh)

            default_speed_mps = default_speed_kmh * 1000 / 3600

            G_with_traffic_weights[u][v][key]['travel_time'] = length_meters / default_speed_mps if default_speed_mps > 0 else float('inf')
            G_with_traffic_weights[u][v][key]['congestion_level'] = 0.0
            G_with_traffic_weights[u][v][key]['categoria_congestion'] = "Baja"
            G_with_traffic_weights[u][v][key]['tipo_via_osm'] = data.get('highway', 'N/A')
            G_with_traffic_weights[u][v][key]['length'] = length_meters
            G_with_traffic_weights[u][v][key]['speed_kmh'] = default_speed_kmh
    try:
        if orig_node not in G_with_traffic_weights or dest_node not in G_with_traffic_weights:
            raise HTTPException(status_code=400, detail="Uno o ambos nodos de origen/destino no se encontraron en el grafo.")

        num_alternative_routes = 3
        found_routes_details = []
        temp_G_for_alternatives = copy.deepcopy(G_with_traffic_weights)
        found_node_paths = []

        for i in range(num_alternative_routes * 5):
            try:
                current_route_nodes = nx.shortest_path(temp_G_for_alternatives, source=orig_node, target=dest_node, weight='travel_time')

                if current_route_nodes in found_node_paths:
                    logger.info(f"Ruta duplicada encontrada (intento {i+1}), buscando otra.")
                    for u, v in zip(current_route_nodes[:-1], current_route_nodes[1:]):
                        if temp_G_for_alternatives.has_edge(u, v):
                            for key in list(temp_G_for_alternatives[u][v].keys()):
                                if 'travel_time' in temp_G_for_alternatives[u][v][key]:
                                    temp_G_for_alternatives[u][v][key]['travel_time'] *= 100000
                    continue

                route_details = get_route_details(G_with_traffic_weights, current_route_nodes)

                found_routes_details.append(route_details)
                found_node_paths.append(current_route_nodes)
                logger.info(f"Ruta alternativa {len(found_routes_details)} encontrada con {len(current_route_nodes)} nodos. Tiempo: {route_details.tiempo_total_viaje_minutos:.2f} min. Congestión: {route_details.overall_congestion:.2f}")

                if len(found_routes_details) >= num_alternative_routes:
                    break

                for u, v in zip(current_route_nodes[:-1], current_route_nodes[1:]):
                    if temp_G_for_alternatives.has_edge(u, v):
                        for key in list(temp_G_for_alternatives[u][v].keys()):
                            if 'travel_time' in temp_G_for_alternatives[u][v][key]:
                                temp_G_for_alternatives[u][v][key]['travel_time'] *= 1000

            except nx.NetworkXNoPath:
                logger.warning(f"No se encontró más rutas alternativas entre {orig_node} y {dest_node}.")
                break

        found_routes_details.sort(key=lambda r: r.tiempo_total_viaje_segundos)

        if not found_routes_details:
            raise HTTPException(status_code=404, detail="No se encontró ninguna ruta entre el origen y el destino especificados.")

        return MultiRouteResponse(
            mensaje="Rutas calculadas exitosamente.",
            nodo_origen_osmid=orig_node,
            nodo_destino_osmid=dest_node,
            rutas_alternativas=found_routes_details
        )

    except nx.NetworkXNoPath:
        logger.warning(f"No se encontró una ruta entre {orig_node} y {dest_node}.")
        raise HTTPException(status_code=404, detail="No se encontró una ruta entre el origen y el destino especificados.")
    except Exception as e:
        logger.error(f"Error al calcular la ruta: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al calcular la ruta: {e}")

from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
