import rasterio
import numpy as np
import requests
import matplotlib.pyplot as plt
import os
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
from pyproj import Transformer

# --- 1. CONFIGURACIÓN ---
API_KEY = "btE095QcU55D34q4pM99KKBBO8YiRO2INIT3B7B1471kZ6rF5NP98j39G1SZ54SS" # Recuerda protegerla en el entorno final
ARCHIVO_MDT = "terreno.tif"
ARCHIVO_COMBUSTIBLE = "combustible.tif"
SALIDA_ROS = "mapa_ros_dinamico.tif"
CARPETA_IMAXES = "06_imagenes" # Carpeta para guardar los resultados visuales

# Crear carpeta de imágenes si no existe
if not os.path.exists(CARPETA_IMAXES):
    os.makedirs(CARPETA_IMAXES)

# --- 2. FUNCIÓN DE MUESTREO ESPACIAL (MeteoGalicia API v5) ---
def obtener_meteo_dinamica(api_key, bounds, crs_raster, rows, cols):
    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    lon_min, lat_min = transformer_to_wgs84.transform(bounds.left, bounds.bottom)
    lon_max, lat_max = transformer_to_wgs84.transform(bounds.right, bounds.top)

    n_puntos = 4 
    lons = np.linspace(lon_min, lon_max, n_puntos)
    lats = np.linspace(lat_min, lat_max, n_puntos)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    
    puntos_coords = [f"{lon:.4f},{lat:.4f}" for lon, lat in zip(grid_lon.flatten(), grid_lat.flatten())]
    coords_str = ";".join(puntos_coords) 

    url = "https://servizos.meteogalicia.gal/apiv5/getNumericForecastInfo"
    params = {
        "coords": coords_str,
        "variables": "wind,relative_humidity", 
        "models": "WRF,WRF", # Relación 1:1 variables/modelos
        "format": "application/json",
        "API_KEY": api_key
    }

    print(f"📡 Solicitando datos a MeteoGalicia (Vento e Humidade)...")
    response = requests.get(url, params=params)
    data = response.json()

    if 'exception' in data:
        print(f"❌ EXCEPCIÓN DA API: {data['exception']['message']} (Código: {data['exception']['code']})")
        return None, None, None

    puntos_u, puntos_v, puntos_rh, puntos_pos = [], [], [], []
    transformer_to_utm = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)

    for feature in data['features']:
        if 'properties' not in feature: continue
        vel, direccion, humedad = 0.0, 0.0, 50.0
        
        vars_list = feature['properties']['days'][0]['variables']
        for v in vars_list:
            if v['name'] == 'wind':
                vel = v['values'][0]['moduleValue']
                direccion = v['values'][0]['directionValue']
            elif v['name'] == 'relative_humidity':
                humedad = v['values'][0]['value']
        
        lon_wgs, lat_wgs = feature['geometry']['coordinates'] 
        x_utm, y_utm = transformer_to_utm.transform(lon_wgs, lat_wgs)

        rad = np.radians((direccion + 180) % 360)
        puntos_u.append(vel * np.sin(rad))
        puntos_v.append(vel * np.cos(rad))
        puntos_rh.append(humedad)
        puntos_pos.append((x_utm, y_utm))

    puntos_pos = np.array(puntos_pos)
    target_x = np.linspace(bounds.left, bounds.right, cols)
    target_y = np.linspace(bounds.top, bounds.bottom, rows)
    target_x_grid, target_y_grid = np.meshgrid(target_x, target_y)

    print("🧩 Interpolando Vento e Humidade con método cúbico...")
    U_interp = griddata(puntos_pos, puntos_u, (target_x_grid, target_y_grid), method='cubic')
    V_interp = griddata(puntos_pos, puntos_v, (target_x_grid, target_y_grid), method='cubic')
    RH_interp = griddata(puntos_pos, puntos_rh, (target_x_grid, target_y_grid), method='cubic')

    return U_interp, V_interp, RH_interp

# --- 3. PROCESAMIENTO GEOSPAZIAL E CÁLCULO ---
try:
    with rasterio.open(ARCHIVO_MDT) as src:
        elevacion = src.read(1).astype(float)
        elevacion[elevacion == src.nodata] = np.nan
        meta = src.meta.copy(); bounds = src.bounds
        crs_raster = src.crs; rows, cols = elevacion.shape
        cell_size = src.transform[0]

    with rasterio.open(ARCHIVO_COMBUSTIBLE) as src_c:
        combustible = src_c.read(1)

    U_viento, V_viento, Mapa_Humedad = obtener_meteo_dinamica(API_KEY, bounds, crs_raster, rows, cols)

    if U_viento is not None:
        # 1. Limpieza y Suavizado (Gaussian Filter para evitar "cicatrices" de interpolación)
        U_viento = np.where(np.isnan(U_viento), np.nanmean(U_viento), U_viento)
        V_viento = np.where(np.isnan(V_viento), np.nanmean(V_viento), V_viento)
        Mapa_Humedad = np.where(np.isnan(Mapa_Humedad), np.nanmean(Mapa_Humedad), Mapa_Humedad)
        
        # Suavizado ligero para estética
        U_viento = gaussian_filter(U_viento, sigma=2)
        V_viento = gaussian_filter(V_viento, sigma=2)

        # 🔴 2. BLOQUE DE AUDITORÍA SEGREGADA (VISUALIZACIÓN SEPARADA)
        
        # --- AUDITORÍA 1: CAMPO VECTORIAL DEL VIENTO (Separado) ---
        print("📸 Xerando auditoría visual do Vento (Paso 1 de 2)...")
        plt.figure(figsize=(12, 10)) # Tamaño grande y cuadrado
        
        # Fondo topográfico
        plt.imshow(elevacion, cmap='terrain', alpha=0.5)
        
        # Flechas de viento (Quiver plot)
        stride = max(rows // 30, 1) # Control de densidad de flechas
        y_g, x_g = np.mgrid[0:rows:stride, 0:cols:stride]
        plt.quiver(x_g, y_g, U_viento[::stride, ::stride], -V_viento[::stride, ::stride], 
                   color='darkblue', scale=150, width=0.003, headwidth=4)
        
        # Formateo profesional
        plt.title("Auditoría: Campo Vectorial do Vento (MeteoGalicia WRF)", fontsize=16, fontweight='bold')
        plt.xlabel("Columnas (UTM - Metros)", fontsize=12)
        plt.ylabel("Filas (UTM - Metros)", fontsize=12)
        plt.grid(True, color='grey', linestyle='--', linewidth=0.5, alpha=0.5)
        
        # Mostrar Viento (Bloquea la ejecución hasta cerrar la ventana)
        print("👉 Pecha a xanela do gráfico de Vento para continuar coa Humidade...")
        plt.show()

        # --- AUDITORÍA 2: MAPA TÉRMICO DE HUMEDAD RELATIVA (Separado) ---
        print("📸 Xerando auditoría visual da Humidade (Paso 2 de 2)...")
        plt.figure(figsize=(12, 10)) # Tamaño grande y cuadrado
        
        # Fondo topográfico suave
        plt.imshow(elevacion, cmap='terrain', alpha=0.3)
        
        # Mapa de calor de humedad (Yellow-Green-Blue)
        im_rh = plt.imshow(Mapa_Humedad, cmap='YlGnBu', alpha=0.7)
        
        # Contornos con etiquetas para resaltar cambios
        contour_rh = plt.contour(Mapa_Humedad, levels=5, colors='white', linewidths=0.5, alpha=0.5)
        plt.clabel(contour_rh, inline=True, fontsize=10, fmt='%1.0f%%')
        
        # Barra de color profesional
        plt.colorbar(im_rh, label='Humidade Relativa (%)', fraction=0.046, pad=0.04)
        
        # Formateo profesional
        plt.title("Auditoría: Distribución da Humidade Relativa (%)", fontsize=16, fontweight='bold')
        plt.xlabel("Columnas (UTM - Metros)", fontsize=12)
        plt.ylabel("Filas (UTM - Metros)", fontsize=12)
        
        # Mostrar Humedad
        print("👉 Pecha a xanela do gráfico de Humidade para rematar o cálculo de Rothermel...")
        plt.show()

        # --- 3. Resto del Cálculo de Rothermel (sin cambios) ---
        print("🔥 Calculando propagación final (Suma vectorial de tensores)...")
        dy, dx = np.gradient(elevacion, cell_size)
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        aspect_rad = np.arctan2(-dx, dy)
        Phi_S = 5.275 * (np.tan(slope_rad)**2)
        Sx, Sy = Phi_S * np.sin(aspect_rad + np.pi), Phi_S * np.cos(aspect_rad + np.pi)

        VALORES_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
        R0 = np.zeros_like(combustible, dtype=float)
        for m, v in VALORES_R0.items(): R0[combustible == m] = v

        Push_X, Push_Y = Sx + (0.05 * U_viento), Sy + (0.05 * V_viento)
        Phi_Total = np.sqrt(Push_X**2 + Push_Y**2)
        
        # Factor Humedad (Amortiguación termodinámica)
        Factor_Humedad = np.ones_like(Mapa_Humedad)
        Factor_Humedad = np.where((Mapa_Humedad >= 30) & (Mapa_Humedad < 60), 0.7, Factor_Humedad)
        Factor_Humedad = np.where((Mapa_Humedad >= 60) & (Mapa_Humedad < 80), 0.4, Factor_Humedad)
        Factor_Humedad = np.where(Mapa_Humedad >= 80, 0.1, Factor_Humedad)

        ROS_final = R0 * (1 + Phi_Total) * Factor_Humedad
        ROS_final = np.nan_to_num(ROS_final, nan=0.0)

        # 4. Exportación (sin cambios)
        meta.update(dtype='float32', nodata=-9999.0)
        with rasterio.open(SALIDA_ROS, 'w', **meta) as dst:
            dst.write(ROS_final.astype('float32'), 1)
        print(f"✅ Ficheiro de saída de ROS Dinámico gardado exitosamente: {SALIDA_ROS}")

except Exception as e:
    print(f"❌ Erro crítico no procesamento: {e}")