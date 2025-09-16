CREATE DATABASE huaraz_rutas OWNER postgres;
CREATE EXTENSION postgis;
SELECT postgis_full_version();

SELECT COUNT(*) FROM nodes; -- contador de los nodos


SELECT osmid, name, highway, length, ST_AsText(geometry) FROM edges LIMIT 5;

create table datos_trafico (
	id SERIAL primary key,
	u BIGINT not null, -- Nodo de origen de la arista 
	v BIGINT not null, -- Nodo de destino de la arista 
	edge_key BIGINT not null, -- clave de arista (para aristas múltiples entre u y v)
    timestamp TIMESTAMPTZ default CURRENT_TIMESTAMP, -- Momento en que se registró/predijo el tráfico
	dia_de_semana INTEGER not null, -- Día de la semana (0=Lunes, ..., 6=Domingo)
	hora_del_dia INTEGER not null, -- Hora del día (0-23)
	velocidad_promedio_kmh REAL, -- Velocidad promedio observada/predicha en km/h
	nivel_congestion REAL, -- Nivel de congestión (ej. 0.0 = sin congestión, 1.0 = muy congestionado)
	tiempoViajeEstimadoSegundos REAL, -- Tiempo de viaje estimado para esta arista en segundos (CLAVE PARA RASTREO)
    
	-- Agregamos una restricción UNIQUE para evitar duplicados en la misma arista, día y hora.
    -- Esto es importante para el modelo de IA.
    UNIQUE (u, v, edge_key,dia_de_semana, hora_del_dia)
);

SELECT u, v, key, name, length FROM edges LIMIT 5;

-- Insert de datos ejemplo de prueba
-- Insertar un escenario de tráfico "ligero" para el viernes a las 3 PM
INSERT INTO datos_trafico (u, v, edge_key, dia_de_semana, hora_del_dia, velocidad_promedio_kmh, nivel_congestion, tiempoViajeEstimadoSegundos) VALUES
(287840918, 4681487920, 0, 4, 15, 25.0, 0.2, (34.006350864235706 / (25.0 * 1000 / 3600))); -- Longitud / Velocidad_en_m_por_seg

-- Insertar un escenario de tráfico "moderado" para el viernes a las 6 PM
INSERT INTO datos_trafico (u, v, edge_key, dia_de_semana, hora_del_dia, velocidad_promedio_kmh, nivel_congestion, tiempoViajeEstimadoSegundos) VALUES
(287840918, 4681487920, 0, 4, 18, 15.0, 0.6, (34.006350864235706 / (15.0 * 1000 / 3600)));

-- Insertar un escenario de tráfico "pesado" para el viernes a las 8 AM (hora punta matutina)
INSERT INTO datos_trafico (u, v, edge_key, dia_de_semana, hora_del_dia, velocidad_promedio_kmh, nivel_congestion, tiempoViajeEstimadoSegundos) VALUES
(287840918, 4681487920, 0, 4, 8, 8.0, 0.9, (34.006350864235706 / (8.0 * 1000 / 3600)));

-- NOTA: El cálculo de tiempoViajeEstimadoSegundos = Longitud_metros / (Velocidad_kmh * 1000 / 3600)
-- 1000/3600 es para convertir km/h a m/s.
-- Por ejemplo, para la primera: 34.006350864235706 / (25 * 1000 / 3600) = 34.006350864235706 / 6.9444... = aprox 4.9 segundos.
SELECT Count* FROM nodes;