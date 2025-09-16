import redis

try:
    # Conéctate a Redis. localhost es la dirección por defecto.
    # El puerto es 6379 (el que mapeamos con -p 6379:6379)
    # db=0 es la base de datos por defecto de Redis
    r = redis.StrictRedis(host='localhost', port=6379, db=0)

    # Prueba a establecer una clave-valor
    r.set('mensaje_bienvenida', 'Hola desde Redis en Huaraz Rutas Inteligentes!')
    print("Clave 'mensaje_bienvenida' establecida con éxito.")

    # Recupera el valor
    value = r.get('mensaje_bienvenida')
    print(f"Valor recuperado de Redis: {value.decode('utf-8')}")

    # Prueba a incrementar un contador
    r.incr('visitas')
    r.incr('visitas')
    current_visitas = r.get('visitas')
    print(f"Contador 'visitas' actual: {current_visitas.decode('utf-8')}")

    # Limpia la clave de prueba (opcional)
    # r.delete('mensaje_bienvenida')
    # r.delete('visitas')
    # print("Claves de prueba eliminadas.")

except redis.exceptions.ConnectionError as e:
    print(f"ERROR: No se pudo conectar a Redis. Asegúrate de que el contenedor 'rutas-huaraz-redis' esté en ejecución.")
    print(f"Detalles del error: {e}")
except Exception as e:
    print(f"Ocurrió un error inesperado: {e}")