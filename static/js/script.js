// Coordenadas iniciales para centrar el mapa (Huaraz, Perú)
const huarazLat = -9.529;
const huarazLon = -77.529;

// Declaraciones de variables globales. Se inicializan en DOMContentLoaded.
let map = null;
let routePolylines = [];
let originMarker = null;
let destinationMarker = null;
let clickMode = null; // 'origin' o 'destination'

// Nuevos elementos del DOM para la congestión general en el resumen y el modal
let summaryOverallCongestion = null;
let modalOverallCongestionCategory = null; 
let modalTotalDistance = null;
let modalTotalDuration = null;
let segmentDetailsBody = null; 

let modalTitleElement = null; 

let currentRouteSegments = []; 


// --- FUNCIONES AUXILIARES ---

/**
 * Función para buscar una ubicación usando Nominatim (autocompletado).
 * Llamada por onkeyup en los inputs de búsqueda y por el focus event listener.
 */
async function searchLocation(type) {
    const searchInput = document.getElementById(`${type}Search`);
    const resultsDiv = document.getElementById(`${type}SearchResults`);

    if (!searchInput || !resultsDiv) {
        console.warn(`Advertencia: Elemento con ID '${type}Search' o '${type}SearchResults' no encontrado. Intentando de nuevo más tarde si DOMContentLoaded no ha terminado.`);
        return;
    }

    resultsDiv.innerHTML = '';
    resultsDiv.style.display = 'none';

    const queryText = searchInput.value;

    if (queryText.length < 3) {
        if (queryText.length > 0) { // Muestra el mensaje solo si el usuario ha empezado a escribir
            resultsDiv.innerHTML = '<div>Escribe al menos 3 caracteres para buscar.</div>';
            resultsDiv.style.display = 'block';
        }
        return;
    }

    const query = encodeURIComponent(`${queryText}, Huaraz, Peru`);
    const nominatimUrl = `https://nominatim.openstreetmap.org/search?q=${query}&format=json&limit=5`;

    try {
        const response = await fetch(nominatimUrl);
        const data = await response.json();


        data.forEach(result => {
            const div = document.createElement('div');
            div.textContent = result.display_name;
            div.onclick = () => {
                searchInput.value = result.display_name;
                document.getElementById(`${type}Lat`).value = parseFloat(result.lat).toFixed(6);
                document.getElementById(`${type}Lon`).value = parseFloat(result.lon).toFixed(6);

                document.getElementById(`${type}CoordsDisplay`).style.display = 'block';

                resultsDiv.innerHTML = '';
                resultsDiv.style.display = 'none';

                updateMarker(type, result.lat, result.lon);

                if (map) {
                    map.setView([result.lat, result.lon], 16);
                }
            };
            resultsDiv.appendChild(div);
        });
        resultsDiv.style.display = 'block';

    } catch (error) {
        console.error("Error al buscar ubicación:", error);
        resultsDiv.innerHTML = '<div>Error al buscar. Intenta de nuevo.</div>';
        resultsDiv.style.display = 'block';
    }
}

/**
 * Función para actualizar o crear un marcador en el mapa.
 */
function updateMarker(type, lat, lon) {
    if (!map) {
        console.warn("Advertencia: Intento de actualizar marcador antes de que el mapa esté inicializado.");
        return;
    }

    const markerCoords = [lat, lon];
    if (type === 'origin') {
        if (originMarker) map.removeLayer(originMarker);
        originMarker = L.marker(markerCoords).addTo(map)
            .bindPopup("<b>Origen</b>").openPopup();
    } else if (type === 'destination') {
        if (destinationMarker) map.removeLayer(destinationMarker);
        destinationMarker = L.marker(markerCoords).addTo(map)
            .bindPopup("<b>Destino</b>").openPopup();
    }
}

/**
 * Función para manejar clics en el mapa.
 */
function handleMapClick(e) {
    const lat = e.latlng.lat.toFixed(6);
    const lon = e.latlng.lng.toFixed(6);

    if (!clickMode) {
        alert("Haz clic en el campo 'Origen' o 'Destino' primero, y luego en el mapa para seleccionar.");
        return;
    }

    const originResults = document.getElementById('originSearchResults');
    const destResults = document.getElementById('destinationSearchResults');
    if (originResults) originResults.style.display = 'none';
    if (destResults) destResults.style.display = 'none';

    if (clickMode === 'origin') {
        document.getElementById('originLat').value = lat;
        document.getElementById('originLon').value = lon;
        document.getElementById('originSearch').value = `Lat: ${lat}, Lon: ${lon} (Desde mapa)`;
        document.getElementById('originCoordsDisplay').style.display = 'block';
        updateMarker('origin', lat, lon);
        
    } else if (clickMode === 'destination') {
        document.getElementById('destinationLat').value = lat;
        document.getElementById('destinationLon').value = lon;
        document.getElementById('destinationSearch').value = `Lat: ${lat}, Lon: ${lon} (Desde mapa)`;
        document.getElementById('destinationCoordsDisplay').style.display = 'block';
        updateMarker('destination', lat, lon);
        
    }
    clickMode = null;
}

/**
 * Función para formatear segundos a HH:MM:SS.
 */
function formatTime(totalSeconds) {
    if (typeof totalSeconds !== 'number' || isNaN(totalSeconds)) {
        return '--:--:--';
    }
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    const pad = (num) => num.toString().padStart(2, '0');
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

/**
 * Función para mostrar más detalles de una ruta en un modal.
 */
function showMoreDetails(routeIndex, routeData) {
    const modal = document.getElementById('routeDetailsModal');

    if (!modal || !modalTotalDistance || !modalTotalDuration || !modalOverallCongestionCategory || !segmentDetailsBody || !modalTitleElement) {
        console.error("Error: Uno o más elementos de la modal no encontrados en el DOM. Asegúrate de que los IDs sean correctos en el HTML y se inicialicen en DOMContentLoaded.");
        alert("Error al mostrar los detalles de la ruta. Faltan elementos en el HTML.");
        return;
    }

    // Definir los colores y etiquetas para las 3 rutas
    const routeDisplayInfo = [
        { type: 'Ruta Óptima',  color: '#00ff0092' }, // Verde
        { type: 'Ruta Alternativa', color: '#ffff0089' }, // Amarillo
        { type: 'Ruta Turística', color: '#ff000089' }  // Rojo
    ];
    const displayInfo = routeDisplayInfo[routeIndex] || { type: `Ruta ${routeIndex + 1}`, congestionLevel: 'Desconocido', color: '#FFFFFF' };

    modalTitleElement.textContent = `Detalles de ${displayInfo.type}`;

    modalTotalDistance.textContent = `${(routeData.total_distance_meters / 1000).toFixed(2)} km`;
    modalTotalDuration.textContent = formatTime(routeData.tiempo_total_viaje_segundos);

    // Mostrar la CATEGORÍA de congestión general (Baja, Media, Alta) del backend
    // Y asignar el color correspondiente basado en esa categoría.
    modalOverallCongestionCategory.textContent = routeData.overall_congestion_category;
    let overallCongestionColor;
    if (routeData.overall_congestion_category === 'Baja') {
        overallCongestionColor = '#00FF00'; // Verde
    } else if (routeData.overall_congestion_category === 'Media') {
        overallCongestionColor = '#FFFF00'; // Amarillo
    } else if (routeData.overall_congestion_category === 'Alta') {
        overallCongestionColor = '#FF0000'; // Rojo
    } else {
        overallCongestionColor = 'inherit'; // Por si acaso
    }
    modalOverallCongestionCategory.style.color = overallCongestionColor;

    // Poblar la tabla de detalles de los segmentos
    segmentDetailsBody.innerHTML = ''; // Limpiar segmentos anteriores
   
    if (routeData.segmentos_de_ruta && routeData.segmentos_de_ruta.length > 0) {
        routeData.segmentos_de_ruta.forEach((segment, segIndex) => {
            const row = segmentDetailsBody.insertRow();

            // Determinar el color para la columna Nivel Congestión (%)
            // Esta lógica debe ser consistente con la de Python para los umbrales
            let segmentCongestionColor = 'inherit'; // Por defecto
            if (segment.congestion_level < 0.3) {
                segmentCongestionColor = 'green'; // Baja
            } else if (segment.congestion_level >= 0.3 && segment.congestion_level < 0.7) {
                segmentCongestionColor = 'yellow'; // Media
            } else { // congestion_level >= 0.7
                segmentCongestionColor = 'red'; // Alta
            }

            // Columna 1: Segmento (De -> A) - Combinamos lat/lon de inicio y fin
            row.insertCell().textContent = `Sg. ${segIndex + 1}: (${segment.start_lat.toFixed(6)}, ${segment.start_lon.toFixed(6)}) -> (${segment.end_lat.toFixed(6)}, ${segment.end_lon.toFixed(6)})`;

            // Columna 2: Tipo de Vía (OSM)
            row.insertCell().textContent = segment.tipo_via_osm;

            // Columna 3: Longitud (m)
            row.insertCell().textContent = segment.length_meters.toFixed(1);

            // Columna 4: Velocidad (km/h)
            row.insertCell().textContent = segment.speed_kmh.toFixed(1);

            // Columna 5: Nivel Congestión (%) y color
            const congestionCell = row.insertCell();
            congestionCell.textContent = `${(segment.congestion_level * 100).toFixed(1)}%`;
            congestionCell.style.color = segmentCongestionColor;

            // Usamos DIRECTAMENTE segment.categoria_congestion del backend/base de datos
            row.insertCell().textContent = segment.categoria_congestion;

            // Columna 7: Tiempo (s)
            row.insertCell().textContent = segment.travel_time_seconds.toFixed(1);
        });
    } else {
        const row = segmentDetailsBody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 7; 
        cell.textContent = 'No hay detalles de segmentos disponibles.';
        cell.style.textAlign = 'center';
    }

    modal.style.display = 'flex'; // Mostrar el modal
}

/**
 * Función para cerrar el modal.
 */
function closeModal() {
    const modal = document.getElementById('routeDetailsModal');
    modal.style.display = 'none'; 
}

/**
 * Función para calcular y mostrar múltiples rutas.
 */
async function calculateAndDisplayRoute() {
    const originLat = parseFloat(document.getElementById('originLat').value);
    const originLon = parseFloat(document.getElementById('originLon').value);
    const destLat = parseFloat(document.getElementById('destinationLat').value);
    const destLon = parseFloat(document.getElementById('destinationLon').value);

    if (isNaN(originLat) || isNaN(originLon) || isNaN(destLat) || isNaN(destLon) ||
        !originMarker || !destinationMarker) {
        alert("Por favor, selecciona o ingresa coordenadas válidas para Origen y Destino.");
        return;
    }

    // Limpiar todas las polilíneas de las rutas anteriores
    routePolylines.forEach(polyline => map.removeLayer(polyline));
    routePolylines = [];

    if (!map) {
        console.error("Error: El mapa no está inicializado al intentar calcular la ruta.");
        return;
    }

    // Ajustar los límites del mapa para mostrar los marcadores iniciales
    const bounds = L.latLngBounds(originMarker.getLatLng(), destinationMarker.getLatLng());
    map.fitBounds(bounds.pad(0.5));

    try {
        const response = await fetch('/calculate_route', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                origin: { lat: originLat, lon: originLon },
                destination: { lat: destLat, lon: destLon }
            })
        });
        const data = await response.json();

        if (response.status !== 200) { 
            alert('Error en el cálculo de la ruta: ' + (data.detail || JSON.stringify(data)));
            console.error('API Error:', data);
            const routeSummariesDiv = document.getElementById('routeSummaries');
            if (routeSummariesDiv) {
                routeSummariesDiv.innerHTML = '<div>Error al calcular la ruta.</div>';
            }
            return;
        }

        const routeSummariesDiv = document.getElementById('routeSummaries');
        if (!routeSummariesDiv) {
            console.error("Error: Elemento 'routeSummaries' no encontrado en el DOM. No se pueden mostrar los resúmenes de ruta.");
            alert("Error interno: No se pudo encontrar el área para mostrar los resúmenes de ruta.");
            return;
        }
        routeSummariesDiv.innerHTML = ''; 

        if (data.rutas_alternativas && data.rutas_alternativas.length > 0) {
            let allRoutesBounds = null;

            // Ordenar las rutas por su tiempo de viaje (de la más rápida a la más lenta)
            data.rutas_alternativas.sort((a, b) => a.tiempo_total_viaje_segundos - b.tiempo_total_viaje_segundos);

            // Definir los colores y etiquetas para las 3 rutas
            const routeDisplayInfo = [
                { type: 'Ruta Óptima', color: '#00FF00' }, // Verde
                { type: 'Ruta Alternativa', color: '#FFFF00' }, // Amarillo
                { type: 'Ruta Turística', color: '#FF0000' }  // Rojo
            ];

            // Crear la cabecera de la "tabla"
            const headerDiv = document.createElement('div');
            headerDiv.className = 'route-summary-header';
            headerDiv.innerHTML = `
                <div class="header-item">Tipo de Ruta</div>
                <div class="header-item">Nivel Congestión</div>
                <div class="header-item">Distancia (km)</div>
                <div class="header-item">Tiempo Estimado</div>
                <div class="header-item"></div> 
            `;
            routeSummariesDiv.appendChild(headerDiv);


            data.rutas_alternativas.forEach((route, index) => {
                console.log(`Detalles de Ruta ${index + 1} (ordenada):`, route);

                const displayInfo = routeDisplayInfo[index] || { type: `Ruta ${index + 1}`, congestionCategory: 'Desconocido', color: '#FFFFFF' };
                const overallColor = displayInfo.color; 

                const overallCongestionPercentage = (route.overall_congestion * 100).toFixed(1); 
                
                const actualCongestionCategory = route.overall_congestion_category;
                let congestionPercentageColor = 'inherit'; 
                
                if (actualCongestionCategory === 'Baja') {
                    congestionPercentageColor = '#00FF00'; 
                } else if (actualCongestionCategory === 'Media') {
                    congestionPercentageColor = '#FFFF00'; 
                } else if (actualCongestionCategory === 'Alta') {
                    congestionPercentageColor = '#FF0000'; 
                }

                const polylineCoords = route.coordenadas_de_ruta.map(coord => [coord.lat, coord.lon]);

                const polyline = L.polyline(polylineCoords, { color: overallColor, weight: 6, opacity: 0.8 }).addTo(map);
                routePolylines.push(polyline); 

                if (!allRoutesBounds) {
                    allRoutesBounds = polyline.getBounds();
                } else {
                    allRoutesBounds.extend(polyline.getBounds());
                }

                const travelTimeFormatted = formatTime(route.tiempo_total_viaje_segundos);
                const distanceKm = typeof route.total_distance_meters === 'number'
                                         ? (route.total_distance_meters / 1000).toFixed(2)
                                         : '--';

                const routeSummaryDivItem = document.createElement('div');
                routeSummaryDivItem.className = 'route-summary-row'; 
                routeSummaryDivItem.innerHTML = `
                    <div class="row-item" style="color:${overallColor};">${displayInfo.type}</div> 
                    <div class="row-item" style="color:${congestionPercentageColor};">${overallCongestionPercentage}%</div> 
                    <div class="row-item">${distanceKm}</div>
                    <div class="row-item">${travelTimeFormatted}</div>
                    <div class="row-item">
                        <button class="show-details-btn" data-route-index="${index}">Detalles</button>
                    </div>
                `;
                routeSummariesDiv.appendChild(routeSummaryDivItem);
            });

            document.querySelectorAll('.show-details-btn').forEach(button => {
                button.onclick = (event) => {
                    const routeIndex = parseInt(event.target.dataset.routeIndex);
                    showMoreDetails(routeIndex, data.rutas_alternativas[routeIndex]);
                };
            });

            if (allRoutesBounds) {
                map.fitBounds(allRoutesBounds.pad(0.1));
            }

        } else {
            routeSummariesDiv.innerHTML = '<div>No se encontraron rutas alternativas.</div>';
        }
    } catch (error) {
        console.error("Error al obtener las rutas:", error);
        alert("Error al calcular la ruta: " + error.message);
        const routeSummariesDiv = document.getElementById('routeSummaries');
        if (routeSummariesDiv) {
            routeSummariesDiv.innerHTML = '<div>Error al calcular la ruta.</div>';
        }
    }
}

// Hacemos las funciones globalmente accesibles para los atributos onkeyup/onclick en el HTML
window.calculateAndDisplayRoute = calculateAndDisplayRoute;
window.searchLocation = searchLocation;
window.showMoreDetails = showMoreDetails; 
window.closeModal = closeModal; 
window.resetApplication = resetApplication; 

/**
 * Función para resetear la aplicación: limpia inputs, marcadores y rutas.
 */
function resetApplication() {
    console.log("Reiniciando aplicación...");

    document.getElementById('originSearch').value = '';
    document.getElementById('originLat').value = '';
    document.getElementById('originLon').value = '';
    document.getElementById('destinationSearch').value = '';
    document.getElementById('destinationLat').value = '';
    document.getElementById('destinationLon').value = '';

    document.getElementById('originCoordsDisplay').style.display = 'none';
    document.getElementById('destinationCoordsDisplay').style.display = 'none';

    if (originMarker) {
        map.removeLayer(originMarker);
        originMarker = null;
    }
    if (destinationMarker) {
        map.removeLayer(destinationMarker);
        destinationMarker = null;
    }

    routePolylines.forEach(polyline => map.removeLayer(polyline));
    routePolylines = []; 

    const routeSummariesDiv = document.getElementById('routeSummaries');
    if (routeSummariesDiv) {
        routeSummariesDiv.innerHTML = `
            <div class="route-summary-header">
                <div class="header-item">Tipo de Ruta</div>
                <div class="header-item">Nivel Congestión</div>
                <div class="header-item">Distancia (km)</div>
                <div class="header-item">Tiempo Estimado (HH:MM:SS)</div>
                <div class="header-item"></div> </div>
            `;
    }

    closeModal();

    clickMode = null;

    if (map) {
        map.setView([huarazLat, huarazLon], 14);
    }
}


// --- INICIALIZACIÓN DEL DOM (TODO LO QUE DEPENDE DEL HTML) ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOMContentLoaded disparado: El DOM está listo.");

    // Inicializar el mapa AQUI (SÓLO UNA VEZ)
    if (!map) {
        map = L.map('map').setView([huarazLat, huarazLon], 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);
        map.on('click', handleMapClick);
    } else {
        console.warn("Advertencia: Intentando reinicializar el mapa, pero ya está inicializado.");
    }
    
    summaryOverallCongestion = document.getElementById('summaryOverallCongestion');
    modalTotalDistance = document.getElementById('modalTotalDistance');
    modalTotalDuration = document.getElementById('modalTotalDuration');
    modalOverallCongestionCategory = document.getElementById('modalOverallCongestionCategory');
    segmentDetailsBody = document.getElementById('segmentDetailsBody');

    modalTitleElement = document.getElementById('modalRouteTitle');
                                                              
    document.addEventListener('click', function(event) {
        const originResults = document.getElementById('originSearchResults');
        const destResults = document.getElementById('destinationSearchResults');
        const originSearchInput = document.getElementById('originSearch');
        const destSearchInput = document.getElementById('destinationSearch');

        if (originSearchInput && originResults && !originSearchInput.contains(event.target) && !originResults.contains(event.target)) {
            originResults.style.display = 'none';
        }
        if (destSearchInput && destResults && !destSearchInput.contains(event.target) && !destResults.contains(event.target)) {
            destResults.style.display = 'none';
        }
    });

    const originSearchInput = document.getElementById('originSearch');
    const destSearchInput = document.getElementById('destinationSearch');

    if (originSearchInput) {
        originSearchInput.addEventListener('focus', () => {
            clickMode = 'origin';
            searchLocation('origin');
        });
    } else {
        console.error("Error: Elemento 'originSearch' no encontrado en el DOM para adjuntar listener de foco.");
    }

    if (destSearchInput) {
        destSearchInput.addEventListener('focus', () => {
            clickMode = 'destination';
            searchLocation('destination');
        });
    } else {
        console.error("Error: Elemento 'destSearch' no encontrado en el DOM para adjuntar listener de foco.");
    }

    const closeModalBtn = document.getElementById('closeModalBtn');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeModal);
    }

    const modal = document.getElementById('routeDetailsModal');
    if (modal) {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal();
            }
        });
    }

    // --- NUEVA FUNCIÓN PARA OBTENER LA UBICACIÓN ACTUAL ---
    /**
     * Obtiene la ubicación actual del usuario usando la API de Geolocation.
     * Actualiza los campos de origen y el marcador en el mapa.
     */
    function locateMe() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude.toFixed(6);
                    const lon = position.coords.longitude.toFixed(6);

                    document.getElementById('originLat').value = lat;
                    document.getElementById('originLon').value = lon;
                    document.getElementById('originSearch').value = `Mi Ubicación Actual (Lat: ${lat}, Lon: ${lon})`;
                    document.getElementById('originCoordsDisplay').style.display = 'block';

                    updateMarker('origin', lat, lon);
                    map.setView([lat, lon], 16); // Centrar mapa en la ubicación actual
                    alert("Ubicación actual obtenida.");
                },
                (error) => {
                    let errorMessage = "No se pudo obtener tu ubicación.";
                    switch (error.code) {
                        case error.PERMISSION_DENIED:
                            errorMessage = "Permiso denegado: Por favor, permite el acceso a tu ubicación.";
                            break;
                        case error.POSITION_UNAVAILABLE:
                            errorMessage = "Ubicación no disponible: No se pudo determinar tu posición.";
                            break;
                        case error.TIMEOUT:
                            errorMessage = "Tiempo de espera agotado: No se pudo obtener la ubicación a tiempo.";
                            break;
                        case error.UNKNOWN_ERROR:
                            errorMessage = "Error desconocido al obtener la ubicación.";
                            break;
                    }
                    alert(errorMessage);
                    console.error("Error al obtener la ubicación:", error);
                },
                {
                    enableHighAccuracy: true, // Intenta obtener la mejor ubicación posible
                    timeout: 10000,          // Tiempo máximo para intentar obtener la ubicación (10 segundos)
                    maximumAge: 0            // No usar una ubicación en caché, obtener una nueva
                }
            );
        } else {
            alert("Tu navegador no soporta la API de Geolocation.");
        }
    }

    // Hacer la nueva función globalmente accesible
    window.locateMe = locateMe;

    // --- NUEVO: Añadir control de ubicación al mapa ---
    // Define un control personalizado de Leaflet
    const LocationControl = L.Control.extend({
        onAdd: function(map) {
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-custom');
            container.style.backgroundColor = 'white';
            container.style.width = '30px';
            container.style.height = '30px';
            container.style.borderRadius = '5px';
            container.style.boxShadow = '0 1px 5px rgba(0,0,0,0.65)';
            container.style.cursor = 'pointer';
            container.style.display = 'flex';
            container.style.justifyContent = 'center';
            container.style.alignItems = 'center';
            container.title = 'Mi ubicación actual'; // Tooltip

            // Usar un SVG para el ícono de localización (similar a Google Maps)
            container.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 0 24 24" width="24px" fill="#000000">
                    <path d="M0 0h24v24H0V0z" fill="none"/>
                    <path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.48 3.52 3.17 6.83 2.71 11H1v2h1.71c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-1.71zM12 20c-3.31 0-6-2.69-6-6s2.69-6 6-6 6 2.69 6 6-2.69 6-6 6z"/>
                </svg>
            `;

            L.DomEvent.on(container, 'click', L.DomEvent.stop).on(container, 'click', locateMe);

            return container;
        },

        onRemove: function(map) {
            // Nada que hacer aquí
        }
    });

    // Añade el control al mapa en la posición deseada (ej. 'topright')
    map.addControl(new LocationControl({ position: 'bottomright' }));
    // --- FIN NUEVO ---
});
