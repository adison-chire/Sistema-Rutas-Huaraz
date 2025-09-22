# GeoRutas Huaraz

Proyecto personal que permite calcular y comparar 3 rutas hacia un destino, considerando distancia, tiempo estimado y nivel de congestión en tiempo real.
Cada ruta incluye una tabla de detalles con información de cada nodo: latitud, longitud, tipo de vía, distancia, velocidad, congestión y tiempo.

<div align="center">
  <img src="/assets/sitema_rutas_hz.gif" alt="Demostración de la calculadora de rutas" style="border: 2px solid #cdc8c8ff; border-radius: 15px;">
</div>

### Capturas de pantalla
<div align="center">
  <img src="/assets/img_principal.png" width="600" alt="Pantalla principal">
  <img src="/assets/img_direc.png" width="600" alt="Ruta calculada">
  <img src="/assets/detalle.png" width="600" alt="Reporte de congestión">
  <img src="/assets/huaraz_map.png" width="600" alt="Reporte de congestión">
</div>

### Características
-   **Cálculo de Rutas**: Encuentra rutas óptimas (con menor tiempo de viaje) y más cortas (con menor distancia).
-   **Visualización Interactiva**: Muestra las rutas calculadas en un mapa interactivo de Huaraz.
-   **Reporte de Estado de Calles**: Permite a los usuarios reportar cierres, tráfico pesado u obstrucciones, que se toman en cuenta para futuros cálculos de ruta.
-   **Búsqueda de Direcciones**: Integra una funcionalidad de búsqueda para encontrar ubicaciones fácilmente por nombre.    

### Tecnologías Utilizadas 

`Python` `FastAPI` `OSMnx` `NetworkX` `HTML` `CSS` `JavaScript` `Leaflet.js` `PostgreSQL` `Docker` `Redis`

### Cómo Correr el Proyecto

Sigue estos pasos para configurar y ejecutar la aplicación en tu entorno local.

#### Requisitos
-   Python 3.8+
-   `pip` (gestor de paquetes de Python)
-   Redis Server (debe estar corriendo en tu máquina; puedes usar Docker: `docker run --name my-redis -p 6379:6379 -d redis`)

#### Pasos
1.  **Clona el repositorio**:
    ```bash
    git clone https://github.com/adison-chire/Sistema-Rutas-Huaraz.git
    cd Sistema-Rutas-Huaraz
    ```
2.  **Crea y activa un entorno virtual**:
    ```bash
    python -m venv venv
    # En Windows
    venv\Scripts\activate
    # En macOS/Linux
    source venv/bin/activate
    ```
3.  **Instala las dependencias**:
    ```bash
    pip install -r requirements.txt
    # O, si no creaste el archivo requirements.txt:
    # pip install fastapi "uvicorn[standard]" redis osmnx networkx
    ```
4.  **Ejecuta el servidor**:
    ```bash
    uvicorn main:app --reload
    ```
5.  **Abre la aplicación**:
    Abre tu navegador y navega a `http://127.0.0.1:8000`.

### Contacto

Si tienes alguna pregunta o sugerencia, no dudes en contactarme:
-   [Portfolio](https://adison-chire.github.io/)
-   [LinkedIn](https://www.linkedin.com/in/adison-chire-1603s/)
-   adichidev03@gmail.com

### Próximas mejoras
- Autenticación de usuarios y perfiles personalizados.
- Versión móvil responsive optimizada.
