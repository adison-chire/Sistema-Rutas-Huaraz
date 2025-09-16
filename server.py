from flask import Flask, request, jsonify
import psycopg2
import os
import networkx as nx
import osmnx as ox
from datetime import datetime
import json # Para manejar los 'key' que pueden ser int o str en G.edges

# --- Configuración de la Base de Datos (debe coincidir con tu script de simulación) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "huaraz_rutas")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "alma94moroni") # ¡Asegúrate de que esta sea tu contraseña real!

GRAPH_PATH = "calles_huaraz.graphml" # Asegúrate de que esté en la misma carpeta

app = Flask(__name__)

# Cargar el grafo globalmente para no recargarlo en cada solicitud
# Es crucial que este grafo sea el mismo que usaste para poblar la DB
try:
    G = ox.load_graphml(GRAPH_PATH)
    # Convertir las claves de los bordes a un formato consistente (ej. str)
    # Esto es importante porque las claves pueden ser int en Python/NetworkX pero pueden tratarse como str en la DB
    # Asegúrate de que tu función de poblamiento también maneje esto si es necesario
    G = nx.MultiDiGraph(G) # Asegúrate de que sea MultiDiGraph si tienes bordes paralelos
    # Convertir claves a string para consistencia con la DB si fuera necesario
    # for u, v, k, d in G.edges(keys=True, data=True):
    #     if not isinstance(k, str):
    #         # Si las claves son números enteros, las almacenamos como números en la DB.
    #         # Si las estamos leyendo como string de la DB, hay que convertirlas de vuelta a int aquí.
    #         pass # No es necesario si NetworkX maneja ints y la DB los guarda como ints
except FileNotFoundError:
    print(f"Error: No se encontró el archivo del grafo en {GRAPH_PATH}. Asegúrate de que el grafo esté disponible.")
    G = None # Manejar el caso donde el grafo no se carga

def get_db_connection():
    """Establece y retorna una conexión a la base de datos PostgreSQL."""
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    return conn

# Función para encontrar la ruta (simplificada para el ejemplo)
# En una aplicación real, aquí usarías un algoritmo de ruta (Dijkstra, A*)
# que considere los pesos dinámicos de las aristas desde la DB.
# Para este ejemplo, solo simularemos que encontramos una ruta con segmentos.
@app.route('/find_route', methods=['GET'])
def find_route():
    if G is None:
        return jsonify({"error": "Grafo no cargado."}), 500

    origin_lat = float(request.args.get('origin_lat'))
    origin_lon = float(request.args.get('origin_lon'))
    destination_lat = float(request.args.get('destination_lat'))
    destination_lon = float(request.args.get('destination_lon'))

    # Obtener el día y la hora actuales para la consulta de tráfico
    now = datetime.now()
    dia_de_semana = now.weekday() # 0 = Lunes, 6 = Domingo
    hora_del_dia = now.hour

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Encuentra los nodos más cercanos en el grafo
        orig_node = ox.distance.nearest_nodes(G, origin_lon, origin_lat)
        dest_node = ox.distance.nearest_nodes(G, destination_lon, destination_lat)

        if not orig_node or not dest_node:
            return jsonify({"error": "No se encontraron nodos cercanos para el origen o destino."}), 404

        # Crear un grafo con pesos dinámicos (tiempos de viaje)
        # Aquí es donde realmente se aplica la lógica de tráfico
        # Para cada arista en G, obtenemos su tiempo de viaje del día/hora actual
        for u, v, k, data in G.edges(keys=True, data=True):
            # Asegúrate de que 'k' sea manejado consistentemente (int o str)
            edge_key_db = str(k) if isinstance(k, int) else k # O int(k) si en la DB se guarda como TEXT y son números

            cur.execute("""
                SELECT tiempoviajeestimadosegundos, categoria_congestion, tipo_via_osm
                FROM datos_trafico
                WHERE u = %s AND v = %s AND edge_key = %s
                  AND dia_de_semana = %s AND hora_del_dia = %s;
            """, (u, v, edge_key_db, dia_de_semana, hora_del_dia))
            
            traffic_data = cur.fetchone()
            if traffic_data:
                travel_time, congestion_category, highway_type = traffic_data
                G[u][v][k]['travel_time'] = travel_time
                G[u][v][k]['congestion_category'] = congestion_category
                G[u][v][k]['tipo_via_osm'] = highway_type
            else:
                # Si no hay datos de tráfico, usar un valor por defecto (ej. longitud)
                # O levantar un error si es crucial tener datos de tráfico para cada arista
                # logger.warning(f"No hay datos de tráfico para el borde ({u}, {v}, {k}) en {dia_de_semana}/{hora_del_dia}")
                G[u][v][k]['travel_time'] = data.get('length', 1) / 10 # Una velocidad asumida si no hay datos
                G[u][v][k]['congestion_category'] = "Desconocida"
                G[u][v][k]['tipo_via_osm'] = data.get('highway', 'N/A')


        # Calcular la ruta usando el tiempo de viaje como peso
        # Se asume que G es un MultiDiGraph
        route = nx.shortest_path(G, orig_node, dest_node, weight='travel_time')

        # Preparar los detalles de los segmentos para la respuesta
        route_segments_details = []
        total_distance = 0
        total_duration = 0
        all_congestion_categories = []

        for i in range(len(route) - 1):
            u = route[i]
            v = route[i+1]
            
            # Los MultiDiGraph pueden tener múltiples aristas entre los mismos nodos,
            # necesitamos encontrar la arista correcta (la que NetworkX usó en el path)
            # o iterar si necesitamos todas las opciones entre u y v
            
            # En el caso de shortest_path de NetworkX, devuelve una lista de nodos,
            # no de aristas. Hay que reconstruir los datos de las aristas.
            # Para esto, tendrías que haber almacenado el 'key' también en la ruta,
            # o asumir que sólo hay una arista 'k=0' si no las especificaste.
            # Para simplificar aquí, asumiré que estamos iterando y obteniendo los datos
            # de la primera arista entre u y v, o la que tenga el menor 'travel_time' si hay múltiples.

            # Si G es un MultiDiGraph, G.get_edge_data(u, v) retorna un dict de dicts
            # donde las claves son las 'keys' de las aristas.
            edges_between_nodes = G.get_edge_data(u, v)
            if edges_between_nodes:
                # Encuentra la arista que fue parte del camino óptimo.
                # Esto es complejo sin saber qué 'key' específico usó shortest_path.
                # Una solución robusta sería que shortest_path devuelva (u, v, key) tuplas.
                # Para este ejemplo, tomaremos la arista con el menor travel_time
                # o la primera si todas son iguales.
                
                # Simplificación: iterar sobre las claves y encontrar la que se usó
                # (en una implementación real, esto sería manejado por el algoritmo de ruteo)
                chosen_edge_key = None
                min_travel_time = float('inf')
                
                for k_edge, edge_attrs in edges_between_nodes.items():
                    if 'travel_time' in edge_attrs and edge_attrs['travel_time'] < min_travel_time:
                        min_travel_time = edge_attrs['travel_time']
                        chosen_edge_key = k_edge
                
                if chosen_edge_key is not None:
                    data = edges_between_nodes[chosen_edge_key]
                    
                    segment_length = data.get('length', 0) # longitud del segmento
                    segment_duration = data.get('travel_time', 0) # tiempo de viaje del segmento
                    segment_congestion = data.get('congestion_category', 'Desconocida')
                    segment_highway_type = data.get('tipo_via_osm', 'N/A')
                    segment_speed = data.get('travel_time') and (segment_length / (segment_duration / 3.6)) if segment_duration > 0 else 0 # km/h

                    total_distance += segment_length
                    total_duration += segment_duration
                    all_congestion_categories.append(segment_congestion)

                    route_segments_details.append({
                        "u": u,
                        "v": v,
                        "key": chosen_edge_key, # El key de la arista
                        "length_meters": segment_length,
                        "tiempoviajeestimadosegundos": segment_duration,
                        "categoria_congestion": segment_congestion,
                        "tipo_via_osm": segment_highway_type,
                        "velocidad_promedio_kmh": segment_speed
                    })
        
        # Calcular la categoría de congestión general (ej. la más frecuente o la peor)
        if all_congestion_categories:
            from collections import Counter
            most_common_congestion = Counter(all_congestion_categories).most_common(1)[0][0]
            # O puedes tener una lógica más sofisticada, ej. si hay un "Alta", la general es "Alta"
        else:
            most_common_congestion = "N/A"

        cur.close()
        conn.close()

        return jsonify({
            "route_found": True,
            "total_distance_meters": total_distance,
            "total_duration_seconds": total_duration,
            "overall_congestion_category": most_common_congestion,
            "segments": route_segments_details,
            "route_nodes": route # También podrías devolver los nodos para dibujar el path en el mapa
        })

    except Exception as e:
        # En un entorno de producción, loggea el error y no expongas los detalles al usuario
        return jsonify({"error": f"Error al calcular la ruta: {str(e)}"}), 500

if __name__ == '__main__':
    # Ejecuta el servidor Flask
    # Para desarrollo: app.run(debug=True)
    # Para producción, usar un servidor WSGI como Gunicorn o Waitress
    print("Iniciando Flask server. Accede a http://127.0.0.1:5000/find_route?origin_lat=...&origin_lon=...&destination_lat=...&destination_lon=...")
    app.run(debug=True) # debug=True recarga el servidor automáticamente al cambiar el código