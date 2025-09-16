import osmnx as ox #libreria para importar datos de OpenStreetMap (OSM) y los convertirlos en un grafo de NetworkX
import matplotlib.pyplot as plt

# Define el lugar de interés
# se puede usar un nombre de ciudad, un punto geográfico, o un polígono
# Para Huaraz, un nombre de lugar debería funcionar bien.

# Coordenadas unasam central 
lat, lon = -9.521471, -77.529300

# Radio en metros alrededor del punto
dist = 3500

# Para descargar la red de calles 
print(f"Descargando la red de calles desde ({lat},{lon}) con {dist} metros de radio");
G = ox.graph_from_point((lat, lon), dist=dist, network_type='drive')

print(f"Número de nodos: {len(G.nodes)}")
print(f"Número de aristas: {len(G.edges)}")

# para visualizar el grafo para verificar
print("Mostrando el grafo (cerrar la ventana para continuar)...")
fig, ax = ox.plot_graph(G, filepath="huaraz_map.png", show=True, close=True, save=True)
print("Grafo guardado como huaraz_map.png")

# Guarda el grafo en un formato que puedas cargar después
# El formato GraphML es bueno para guardar y cargar grafos de NetworkX
print("Guardando el grafo en formato GraphML...")
ox.save_graphml(G, filepath="calles_huaraz.graphml")
print("Grafo guardado como calles_huaraz.graphml")

print("¡Mapa de Huaraz descargado y guardado con éxito!")