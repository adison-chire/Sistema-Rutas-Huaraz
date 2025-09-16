import osmnx as ox
import networkx as nx
import psycopg2
import os
from datetime import datetime, timedelta
import random
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuración de la Base de Datos ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "huaraz_rutas")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "alma94moroni") # ¡Asegúrate de que esta sea tu contraseña real!

GRAPH_PATH = "calles_huaraz.graphml" # Asegúrate de que este sea el nombre correcto de tu archivo de grafo

def get_db_connection():
    """Establece y retorna una conexión a la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        conn.autocommit = False # Desactivar autocommit para control manual
        logger.info("Conexión a PostgreSQL establecida.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error al conectar a la base de datos: {e}")
        raise

def clear_existing_traffic_data(conn):
    """Borra todos los datos existentes de la tabla datos_trafico."""
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM datos_trafico;")
            conn.commit()
            logger.info("Datos existentes en 'datos_trafico' borrados.")
    except psycopg2.Error as e:
        logger.error(f"Error al borrar datos existentes: {e}")
        conn.rollback()
        raise

def get_congestion_category(congestion_level):
    """
    Clasifica el nivel de congestión en Baja, Media o Alta.
    La lógica ha sido ajustada para ser más explícita en los rangos.
    """
    if congestion_level < 0.3:
        return "Baja"
    elif congestion_level >= 0.3 and congestion_level < 0.7:
        return "Media"
    else: # Esto implica congestion_level >= 0.7
        return "Alta"

def simulate_traffic_for_edge(edge_length_meters, day_of_week, hour_of_day, highway_type=None):
    """
    Simula la velocidad promedio y el nivel de congestión para una arista
    dada su longitud, día de la semana, hora del día y tipo de vía (highway_type).
    Se han ajustado los parámetros para simular un comportamiento más realista
    basado en el tipo de vía.
    """
    # Velocidades base (km/h) para diferentes tipos de vías
    base_speed_default = 30  # Calles urbanas generales
    base_speed_fast_flow = 50 # Vías rápidas, autopistas, carreteras
    base_speed_main_avenue = 40 # Avenidas principales, troncales
    base_speed_slow_street = 15 # Zonas escolares, callejones, calles en construcción
    base_speed_very_slow = 5  # Escaleras, peatonales (muy baja velocidad para vehículos)
    base_speed_closed = 1    # Calle cerrada (efectivamente bloqueada o con paso mínimo)

    # Definir categorías de vías
    fast_flow_streets = ['secundaria', 'vía rápida', 'autopista', 'carretera']
    main_avenues = ['principal', 'troncal']
    slow_streets = ['zona escolar', 'callejón', 'trocha', 'calle en construccion']
    very_slow_streets = ['escaleras', 'peatonal']
    closed_streets = ['calle cerrada'] # Nueva categoría para impacto extremo

    # Determinar el tipo de vía efectivo, priorizando los más restrictivos
    current_highway_type_effective = 'default' # Valor por defecto
    
    # Asegurarse de que highway_type sea una lista para la iteración
    highway_types_list = []
    if isinstance(highway_type, str):
        highway_types_list = [highway_type]
    elif isinstance(highway_type, list):
        highway_types_list = highway_type
    
    # Priorizar la categoría más restrictiva si la arista tiene múltiples tipos
    for ht in highway_types_list:
        if ht in closed_streets:
            current_highway_type_effective = 'closed'
            break # Es la más restrictiva, no necesitamos seguir buscando
        elif ht in very_slow_streets:
            current_highway_type_effective = 'very_slow' # Más restrictiva que 'slow' o 'default'
        elif ht in slow_streets and current_highway_type_effective not in ['very_slow', 'closed']:
            current_highway_type_effective = 'slow'
        elif ht in fast_flow_streets and current_highway_type_effective not in ['slow', 'very_slow', 'closed']:
            current_highway_type_effective = 'fast_flow'
        elif ht in main_avenues and current_highway_type_effective not in ['slow', 'very_slow', 'closed', 'fast_flow']:
            current_highway_type_effective = 'main_avenue'

    # Establecer parámetros de simulación basados en el tipo de vía efectivo
    if current_highway_type_effective == 'closed':
        base_speed_kmh = base_speed_closed
        congestion_sensitivity = 1.0 # Máxima sensibilidad, siempre congestionado
        random_variance = (0.0, 0.0) # Sin varianza, velocidad constante (muy baja)
    elif current_highway_type_effective == 'very_slow':
        base_speed_kmh = base_speed_very_slow
        congestion_sensitivity = 0.95 # Alta sensibilidad
        random_variance = (-0.02, 0.02)
    elif current_highway_type_effective == 'slow':
        base_speed_kmh = base_speed_slow_street
        congestion_sensitivity = 0.8 # Sensibilidad aumentada
        random_variance = (-0.04, 0.04)
    elif current_highway_type_effective == 'fast_flow':
        base_speed_kmh = base_speed_fast_flow
        congestion_sensitivity = 0.7 # Menor sensibilidad
        random_variance = (-0.06, 0.06)
    elif current_highway_type_effective == 'main_avenue':
        base_speed_kmh = base_speed_main_avenue
        congestion_sensitivity = 0.75 # Sensibilidad moderada
        random_variance = (-0.05, 0.05)
    else: # 'default' o tipo desconocido
        base_speed_kmh = base_speed_default
        congestion_sensitivity = 0.8 # Sensibilidad por defecto
        random_variance = (-0.05, 0.05)

    # Patrones de congestión basados en el día y la hora (lógica existente)
    congestion_patterns = {
        0: { (0, 5): 0.1, (6, 8): 0.9, (9, 11): 0.4, (12, 14): 0.9, (15, 17): 0.7, (18, 23): 0.8 },
        1: { (0, 5): 0.1, (6, 8): 0.9, (9, 11): 0.4, (12, 14): 0.9, (15, 17): 0.7, (18, 23): 0.8 },
        2: { (0, 5): 0.1, (6, 8): 0.9, (9, 11): 0.4, (12, 14): 0.9, (15, 17): 0.7, (18, 23): 0.8 },
        3: { (0, 5): 0.1, (6, 8): 0.9, (9, 11): 0.4, (12, 14): 0.9, (15, 17): 0.7, (18, 23): 0.8 },
        4: { (0, 5): 0.1, (6, 8): 0.9, (9, 11): 0.4, (12, 14): 0.9, (15, 17): 0.7, (18, 23): 0.95 },
        5: { (0, 7): 0.2, (8, 12): 0.6, (13, 17): 0.9, (18, 23): 0.8 },
        6: { (0, 8): 0.2, (9, 16): 0.9, (17, 23): 0.5 }
    }

    current_congestion_factor = 0.3 # Por defecto si no hay patrón que coincida
    for hour_range, factor in congestion_patterns.get(day_of_week, {}).items():
        if hour_range[0] <= hour_of_day <= hour_range[1]:
            current_congestion_factor = factor
            break

    current_congestion_factor += random.uniform(random_variance[0], random_variance[1])
    current_congestion_factor = max(0.0, min(1.0, current_congestion_factor))

    # Calcular la velocidad final basada en la velocidad base y el factor de congestión
    speed_kmh = base_speed_kmh * (1 - current_congestion_factor * congestion_sensitivity)
    speed_kmh = max(1, speed_kmh) # Asegurar que la velocidad sea al menos 1 km/h para evitar división por cero

    # Calcular el tiempo de viaje
    if speed_kmh > 0:
        travel_time_seconds = (edge_length_meters / (speed_kmh * 1000 / 3600))
    else:
        travel_time_seconds = float('inf') # Usar infinito para vías efectivamente bloqueadas
    
        # --- INICIO DE CAMBIO: Ajustar el tiempo de viaje para que sea universalmente más largo ---
    # Este factor (por ejemplo, 1.1) aumenta el tiempo de viaje en un 10%.
    # Puedes ajustar este valor (ej. 1.05 para 5%, 1.2 para 20%) para afinar la duración.
    travel_time_multiplier = 1.1 
    travel_time_seconds *= travel_time_multiplier
    # --- FIN DE CAMBIO ---

    congestion_category = get_congestion_category(current_congestion_factor)

    # Devolvemos el tipo de vía efectivo usado en la simulación
    return speed_kmh, current_congestion_factor, travel_time_seconds, congestion_category, current_highway_type_effective, edge_length_meters

def populate_traffic_data(G, conn):
    """
    Popula la tabla datos_trafico con datos simulados para cada arista
    para todas las horas del día y todos los días de la semana.
    """
    logger.info("Iniciando la población de datos de tráfico simulados...")

    insert_query = """
    INSERT INTO datos_trafico (u, v, edge_key, dia_de_semana, hora_del_dia, 
                               velocidad_promedio_kmh, nivel_congestion, 
                               tiempoviajeestimadosegundos, categoria_congestion, 
                               tipo_via_osm, length) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (u, v, edge_key, dia_de_semana, hora_del_dia) DO UPDATE
    SET velocidad_promedio_kmh = EXCLUDED.velocidad_promedio_kmh,
        nivel_congestion = EXCLUDED.nivel_congestion,
        tiempoviajeestimadosegundos = EXCLUDED.tiempoviajeestimadosegundos,
        categoria_congestion = EXCLUDED.categoria_congestion,
        tipo_via_osm = EXCLUDED.tipo_via_osm,
        length = EXCLUDED.length;
    """

    total_edges = len(G.edges(keys=True, data=True))
    total_inserts = total_edges * 7 * 24 # 7 días * 24 horas
    
    # Usar un cursor para ejecutar muchas inserciones de forma eficiente
    with conn.cursor() as cur:
        processed_count = 0
        batch_size = 5000 # Tamaño del lote para commits
        
        for u, v, key, data in G.edges(keys=True, data=True):
            edge_length = data.get('length')
            if edge_length is None:
                logger.warning(f"Arista ({u}, {v}, {key}) no tiene longitud. Usando longitud por defecto de 50m.")
                edge_length = 50

            # Obtener el tipo de highway
            highway_type = data.get('highway')

            for day_of_week in range(7): # 0 = Lunes, 6 = Domingo
                for hour_of_day in range(24): # 0 a 23
                    speed, congestion_level, travel_time, congestion_category, actual_highway_type, simulated_edge_length = simulate_traffic_for_edge(
                        edge_length, day_of_week, hour_of_day, highway_type
                    )

                    cur.execute(insert_query, (
                        u, v, key, day_of_week, hour_of_day, 
                        speed, congestion_level, travel_time, 
                        congestion_category, actual_highway_type, simulated_edge_length
                    ))
                    processed_count += 1

                    if processed_count % batch_size == 0:
                        conn.commit()
                        logger.info(f"Procesados {processed_count}/{total_inserts} registros. {processed_count/total_inserts*100:.2f}% completado.")
        
        conn.commit() # Commit final para los registros restantes
        logger.info(f"Población de datos de tráfico completada. Total de registros insertados/actualizados: {processed_count}.")

if __name__ == "__main__":
    if not os.path.exists(GRAPH_PATH):
        logger.error(f"Error: El archivo de grafo '{GRAPH_PATH}' no se encontró. Por favor, asegúrate de que esté en la misma carpeta que este script.")
        exit(1)

    try:
        logger.info(f"Cargando grafo de Huaraz desde {GRAPH_PATH}...")
        G = ox.load_graphml(GRAPH_PATH)
        logger.info(f"Grafo cargado: {len(G.nodes)} nodos, {len(G.edges)} aristas.")

        conn = get_db_connection()
        clear_existing_traffic_data(conn)
        populate_traffic_data(G, conn)
        conn.close()
        logger.info("Script de población de datos de tráfico terminado exitosamente.")
    except Exception as e:
        logger.critical(f"El script falló debido a un error: {e}")
