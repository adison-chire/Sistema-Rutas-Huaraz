import psycopg2

# Configura los parámetros de conexión
# Asegúrate de que 'tu_contrasena_postgres' sea la contraseña que usaste
# para el usuario 'postgres' durante la instalación.
DB_HOST = "localhost"
DB_NAME = "huaraz_rutas"
DB_USER = "postgres"
DB_PASS = "alma94moroni" 

try:
    # Intenta conectar a la base de datos
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    print(f"Conexión a la base de datos '{DB_NAME}' exitosa.")

    # Ejecuta una consulta simple para verificar PostGIS
    cur.execute("SELECT postgis_full_version();")
    version_info = cur.fetchone()
    print(f"Versión de PostGIS: {version_info[0]}")

    # Cierra el cursor y la conexión
    cur.close()
    conn.close()
    print("Conexión cerrada.")

except psycopg2.Error as e:
    print(f"ERROR: No se pudo conectar a la base de datos PostgreSQL.")
    print(f"Detalles del error: {e}")
    print("Asegúrate de que PostgreSQL está ejecutándose y que la contraseña y el nombre de la base de datos son correctos.")
except Exception as e:
    print(f"Ocurrió un error inesperado: {e}")