import rasterio
import numpy as np
import matplotlib.pyplot as plt
from skimage.graph import MCP_Geometric

# --- 1. CONFIGURACIÓN ---
ARCHIVO_VELOCIDAD = "velocidad_maxima.tif"
ARCHIVO_FONDO = "terreno.tif"  # Para visualizar de fondo
SALIDA_ISOCRONAS = "isocronas.tif"

# --- 2. CARGAR DATOS ---
try:
    print(f"Abriendo {ARCHIVO_VELOCIDAD}...")
    with rasterio.open(ARCHIVO_VELOCIDAD) as src_ros:
        ros_max = src_ros.read(1)
        # Reemplazar valores no data por 0 para que no ardan
        ros_max = np.where(ros_max == src_ros.nodata, 0.0, ros_max)
        ros_max = np.nan_to_num(ros_max, nan=0.0)
        
        transform = src_ros.transform
        cell_size = transform[0]
        meta = src_ros.meta.copy()

    with rasterio.open(ARCHIVO_FONDO) as src_fondo:
        fondo = src_fondo.read(1)
        fondo = np.where(fondo == src_fondo.nodata, np.nan, fondo)

    # --- 3. MATRIZ DE COSTES ---
    print("Calculando matriz de costes de propagación (minutos/píxel)...")
    # Coste = (Tamaño celda metros) / (Velocidad metros/minuto). Si Velocidad es 0, coste es Infinito
    cost_matrix = np.full_like(ros_max, fill_value=np.inf, dtype=np.float32)
    
    # Máscara de zonas donde el fuego puede avanzar (Velocidad > 0)
    # Evitar divisiones por cero o velocidades microscópicas
    burnable = ros_max > 0.01 
    cost_matrix[burnable] = cell_size / ros_max[burnable]

    # --- 4. ALGORITMO DE PROPAGACIÓN ---
    print("Iniciando simulación de propagación del fuego...")
    
    # Buscar un punto de ignición válido (cerca del centro)
    rows, cols = ros_max.shape
    ignicion_fila, ignicion_col = rows // 2, cols // 2
    
    # Si el centro no es quemable (ej. lago, carretera nula), buscamos el punto quemable más cercano
    if not burnable[ignicion_fila, ignicion_col]:
        print("El centro no es quemable, buscando el punto más cercano...")
        # Encontrar todas las coordenadas quemables
        y_burn, x_burn = np.where(burnable)
        # Calcular distancias al centro
        distancias = (y_burn - ignicion_fila)**2 + (x_burn - ignicion_col)**2
        idx_min = np.argmin(distancias)
        ignicion_fila = y_burn[idx_min]
        ignicion_col = x_burn[idx_min]

    print(f"Punto de ignición establecido en Fila: {ignicion_fila}, Columna: {ignicion_col}")

    # Crear el grafo geométrico con los costes de cada celda
    mcp = MCP_Geometric(cost_matrix)
    
    # Encontrar los costes acumulativos (Tiempo de llegada en minutos al quemar la celda)
    print("Calculando tiempos de llegada (Isocronas) usando Fast Marching (Dijkstra espacial)...")
    tiempos_llegada, _ = mcp.find_costs(starts=[(ignicion_fila, ignicion_col)])
    
    # Enmascarar las celdas inalcanzables (donde el tiempo es infinito o muy alto)
    tiempos_llegada = np.where(tiempos_llegada >= 1e8, np.nan, tiempos_llegada)
    
    print(f"Simulación completa. Tiempo máximo simulado: {np.nanmax(tiempos_llegada)/60:.2f} horas.")

    # --- 5. GUARDAR RESULTADOS (TIEMPOS DE LLEGADA) ---
    meta.update(dtype='float32', count=1, nodata=-9999.0)
    with rasterio.open(SALIDA_ISOCRONAS, 'w', **meta) as dst:
        out_raster = np.where(np.isnan(tiempos_llegada), -9999.0, tiempos_llegada)
        dst.write(out_raster.astype('float32'), 1)
    
    print(f"✅ Mapa de isocronas guardado en '{SALIDA_ISOCRONAS}'")

    # --- 6. VISUALIZACIÓN ---
    print("Generando mapa visual de isocronas...")
    plt.figure(figsize=(12, 10))
    
    # 1. Fondo del terreno
    plt.imshow(fondo, cmap='terrain', alpha=0.6)
    
    # 2. Marcar punto de ignición
    plt.plot(ignicion_col, ignicion_fila, marker='*', color='red', markersize=15, linestyle='None', label='Ignición')

    # 3. Dibujar contornos del tiempo de llegada (Isocronas)
    max_minutos = np.nanmax(tiempos_llegada)
    if max_minutos > 0:
        step_minutos = 60 # Isocronas cada 1 hora (60 mins) por defecto
        if max_minutos <= 120:
            step_minutos = 15 # Cada 15 mins si es rápido (menos de 2h)
        elif max_minutos <= 600:
            step_minutos = 30 # Cada 30 mins si tarda hasta 10h
            
        niveles = np.arange(step_minutos, max_minutos, step_minutos)
        
        # Superponer el avance del fuego
        contour = plt.contour(tiempos_llegada, levels=niveles, colors='red', linewidths=1.5, alpha=0.8)
        plt.clabel(contour, contour.levels, inline=True, fontsize=10, fmt='%1.0f min')

    plt.title(f"Simulación de Propagación del Fuego\nLíneas isocronas de avance cada {step_minutos} min")
    plt.xlabel('Columnas (X)')
    plt.ylabel('Filas (Y)')
    plt.legend()
    plt.colorbar(label='Altitud terreno (m)')
    
    # Añadir un mapa de calor suave debajo de los contornos para las zonas quemadas
    # Usamos np.ma.masked_invalid para no pintar los NaNs
    tiempo_masked = np.ma.masked_invalid(tiempos_llegada)
    im_fire = plt.imshow(tiempo_masked, cmap='YlOrRd', alpha=0.5)
    plt.colorbar(im_fire, label='Tiempo de llegada (Minutos)')

    plt.tight_layout()
    plt.show()

except Exception as e:
    print(f"❌ Error crítico en simulación: {e}")
