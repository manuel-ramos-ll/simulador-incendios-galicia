import rasterio
import numpy as np
import matplotlib.pyplot as plt
from skimage.graph import MCP_Geometric

# --- 1. CONFIGURACIÓN ---
ARCHIVO_VELOCIDAD = "mapa_ros_dinamico.tif" # Conectado co Script 04
ARCHIVO_FONDO = "terreno.tif" 
SALIDA_ISOCRONAS = "isocronas.tif"

# --- 2. CARGAR DATOS E PREPARAR MATRIZ ---
try:
    print(f"Abriendo {ARCHIVO_VELOCIDAD}...")
    with rasterio.open(ARCHIVO_VELOCIDAD) as src_ros:
        ros_max = src_ros.read(1)
        
        # Limpar os -9999.0 do nodata e convertelos a 0.0
        ros_max = np.where(ros_max == src_ros.nodata, 0.0, ros_max)
        ros_max = np.nan_to_num(ros_max, nan=0.0)
        
        transform = src_ros.transform
        cell_size = transform[0]
        meta = src_ros.meta.copy()

    with rasterio.open(ARCHIVO_FONDO) as src_fondo:
        fondo = src_fondo.read(1)
        fondo = np.where(fondo == src_fondo.nodata, np.nan, fondo)

    # --- 3. MATRIZ DE COSTES (FÍSICA DE PROPAGACIÓN) ---
    print("Calculando matriz de costes de propagación (minutos/píxel)...")
    cost_matrix = np.full_like(ros_max, fill_value=np.inf, dtype=np.float32)
    
    # Máscara: O lume só avanza onde a velocidade é minimamente perceptible
    burnable = ros_max > 0.01 
    
    # Tempo = Espazo / Velocidade -> (metros) / (metros/minuto) = minutos
    cost_matrix[burnable] = cell_size / ros_max[burnable]

    # --- 4. ALGORITMO FAST MARCHING ---
    print("Iniciando simulación de propagación del fuego...")
    
    # IGNICIÓN: Para o test independente usamos o centro. 
    # NOTA PARA STREAMLIT: Aquí entrarán as coordenadas X,Y que faga clic o usuario no mapa Folium.
    rows, cols = ros_max.shape
    ignicion_fila, ignicion_col = rows // 2, cols // 2
    
    if not burnable[ignicion_fila, ignicion_col]:
        print("Centro no quemable. Buscando el punto viable más cercano...")
        y_burn, x_burn = np.where(burnable)
        distancias = (y_burn - ignicion_fila)**2 + (x_burn - ignicion_col)**2
        idx_min = np.argmin(distancias)
        ignicion_fila, ignicion_col = y_burn[idx_min], x_burn[idx_min]

    print(f"Ignición en Fila: {ignicion_fila}, Columna: {ignicion_col}")

    # Motor de busca espacial xeométrica (Dijkstra para matrices raster)
    mcp = MCP_Geometric(cost_matrix)
    
    print("Calculando tiempos de llegada (Isocronas)...")
    tiempos_llegada, _ = mcp.find_costs(starts=[(ignicion_fila, ignicion_col)])
    
    # Ocultar celdas inalcanzables (Onde non chegou o lume)
    tiempos_llegada = np.where(tiempos_llegada >= 1e8, np.nan, tiempos_llegada)
    
    print(f"Simulación completa. Tiempo máximo simulado: {np.nanmax(tiempos_llegada)/60:.2f} horas.")

    # --- 5. EXPORTACIÓN ---
    meta.update(dtype='float32', count=1, nodata=-9999.0)
    with rasterio.open(SALIDA_ISOCRONAS, 'w', **meta) as dst:
        out_raster = np.where(np.isnan(tiempos_llegada), -9999.0, tiempos_llegada)
        dst.write(out_raster.astype('float32'), 1)
    
    print(f"✅ Mapa de isocronas guardado en '{SALIDA_ISOCRONAS}'")

    # --- 6. VISUALIZACIÓN E EXPORTACIÓN PARA A MEMORIA ---
    print("Xerando mapa visual de isocronas para a memoria...")
    plt.figure(figsize=(12, 10))
    
    # 1. Fondo do terreo
    plt.imshow(fondo, cmap='terrain', alpha=0.6)
    
    # 2. Marcar punto de ignición
    plt.plot(ignicion_col, ignicion_fila, marker='*', color='blue', markersize=15, linestyle='None', label='Punto de Ignición')

    # 3. Debuxar contornos do tempo de chegada (Isocronas)
    max_minutos = np.nanmax(tiempos_llegada)
    if max_minutos > 0:
        # Lóxica dinámica para os intervalos de tempo (isocronas)
        step_minutos = 60 # Por defecto cada 1 hora
        if max_minutos <= 120:
            step_minutos = 15 # Cada 15 mins se o lume chega rápido
        elif max_minutos <= 600:
            step_minutos = 30 # Cada 30 mins
            
        niveles = np.arange(step_minutos, max_minutos, step_minutos)
        
        # Superpor as liñas de avance do lume
        contour = plt.contour(tiempos_llegada, levels=niveles, colors='red', linewidths=1.5, alpha=0.8)
        plt.clabel(contour, contour.levels, inline=True, fontsize=10, fmt='%1.0f min')

    plt.title(f"Simulación de Propagación do Lume\nLiñas isocronas de avance cada {step_minutos} min", fontsize=14, fontweight='bold')
    plt.xlabel('Columnas (X)')
    plt.ylabel('Filas (Y)')
    plt.legend()
    
    # Engadir un mapa de calor suave debaixo dos contornos
    tiempo_masked = np.ma.masked_invalid(tiempos_llegada)
    im_fire = plt.imshow(tiempo_masked, cmap='YlOrRd', alpha=0.5)
    plt.colorbar(im_fire, label='Tempo de chegada (Minutos)')

    plt.tight_layout()
    
    # Mostrar por pantalla
    plt.show()

except Exception as e:
    print(f"❌ Error crítico en simulación: {e}")