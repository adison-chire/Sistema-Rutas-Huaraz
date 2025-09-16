import osmnx as ox
import psycopg2
from sqlalchemy import create_engine
import geopandas as gpd
import pandas as pd 

# --- Configuración de la Base de Datos ---
DB_HOST = "localhost"
DB_NAME = "huaraz_rutas"
DB_USER = "postgres"
DB_PASS = "alma94moroni" 

# Cadena de conexión para SQLAlchemy (usada por GeoPandas/Pandas)
db_connection_str = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(db_connection_str)

# --- Cargar el Grafo existente ---
graphml_filepath = "calles_huaraz.graphml"
print(f"Cargando el grafo desde: {graphml_filepath}")
G = ox.load_graphml(filepath=graphml_filepath)
print(f"Grafo cargado. Nodos: {len(G.nodes)}, Aristas: {len(G.edges)}")

# --- Exportar nodos y aristas a GeoDataFrames ---
# prepara los datos en un formato tabular compatible con bases de datos espaciales
print("Convirtiendo grafo a GeoDataFrames de nodos y aristas...")
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)

# Limpiar nombres de columnas para compatibilidad con PostGIS si son muy largos o tienen caracteres especiales
nodes_gdf.columns = [col.replace(':', '_') for col in nodes_gdf.columns]
edges_gdf.columns = [col.replace(':', '_') for col in edges_gdf.columns]

# Asegurarse de que los índices son nombres de columnas para que se guarden
nodes_gdf['osmid'] = nodes_gdf.index # osmid ya es un atributo común, pero lo aseguramos
edges_gdf['u'] = edges_gdf.index.get_level_values(0)
edges_gdf['v'] = edges_gdf.index.get_level_values(1)
edges_gdf['key'] = edges_gdf.index.get_level_values(2)


# --- Guardar los GeoDataFrames directamente en PostGIS ---
print(f"Guardando nodos en la tabla '{DB_NAME}.nodes' en PostgreSQL...")
try:
    nodes_gdf.to_postgis("nodes", engine, if_exists="replace", index=False)
    print("Nodos guardados exitosamente.")
except Exception as e:
    print(f"Error al guardar nodos: {e}")

print(f"Guardando aristas en la tabla '{DB_NAME}.edges' en PostgreSQL...")
try:
    edges_gdf.to_postgis("edges", engine, if_exists="replace", index=False)
    print("Aristas guardadas exitosamente.")
except Exception as e:
    print(f"Error al guardar aristas: {e}")

print("Proceso de carga de mapa a la base de datos completado.")