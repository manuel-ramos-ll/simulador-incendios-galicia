import rasterio
import numpy as np
import matplotlib.pyplot as plt

# --- 1. CONFIGURACIÓN DE ARCHIVOS ---
ARCHIVO_MDT = "terreno.tif"  # Mapa de relieve
ARCHIVO_COMBUSTIBLE = "combustible.tif"          # Mapa de combustible
SALIDA_ROS = "velocidad_maxima.tif"

# --- 2. CONFIGURACIÓN METEOROLÓGICA ESTÁTICA  ---
VIENTO_VEL_KMH = 30.0  # Velocidad del viento en km/h
# Dirección DEL viento (De dónde viene): 0=Norte, 90=Este, 180=Sur, 270=Oeste
VIENTO_DIR_GRADOS = 180.0  # Viento del SUR (empuja el fuego hacia el NORTE)

# --- 3. DICCIONARIO DE COMBUSTIBLES (Modelos de Anderson) ---
# Mapeo: Modelo -> Velocidad Base (R0) en metros/minuto (terreno llano, sin viento)
VALORES_R0 = {
    0: 0.0,   # Incombustible (Agua, Asfalto)
    1: 15.0,  # Pastos/Cultivos (Rápido)
    2: 10.0,  # Pasto con matorral
    3: 20.0,  # Pasto alto
    4: 25.0,  # Matorral muy denso/alto (El más rápido y peligroso)
    5: 8.0,   # Matorral bajo
    6: 12.0,  # Matorral inactivo
    7: 6.0,   # Matorral inflamable
    8: 2.0,   # Bosque cerrado, hojarasca compacta (Lento)
    9: 3.5,   # Bosque de pino, hojarasca suelta
    10: 5.0,  # Bosque con sotobosque
    11: 2.5,  # Restos de corta ligeros
    12: 6.0,  # Restos de corta medios
    13: 10.0  # Restos de corta pesados
}

def calcular_pendiente_orientacion(dem, cell_size):
    """Calcula pendiente (grados) y orientación (grados)."""
    dy, dx = np.gradient(dem, cell_size)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect_rad = np.arctan2(-dx, dy)
    aspect_deg = (np.degrees(aspect_rad) + 360) % 360
    return slope_rad, aspect_deg

try:
    print("--- PASO 1: CARGANDO MAPAS ---")
    with rasterio.open(ARCHIVO_MDT) as src_mdt:
        elevacion = src_mdt.read(1)
        elevacion = np.where(elevacion == src_mdt.nodata, np.nan, elevacion)
        cell_size = src_mdt.transform[0]
        meta = src_mdt.meta.copy()

    with rasterio.open(ARCHIVO_COMBUSTIBLE) as src_comb:
        combustible = src_comb.read(1)

    print("--- PASO 2: CALCULANDO VECTORES FÍSICOS ---")
    # 1. Topografía
    slope_rad, aspect_deg = calcular_pendiente_orientacion(elevacion, cell_size)
    
    # 2. Asignar Velocidad Base (R0) usando el diccionario
    R0 = np.zeros_like(combustible, dtype=float)
    for modelo, velocidad in VALORES_R0.items():
        R0[combustible == modelo] = velocidad

    # 3. Factor de Pendiente (Phi_S)
    # Fórmula simplificada: phi_s = c * tan(slope)^2
    C_SLOPE = 5.275 # Constante empírica estándar
    Phi_S = C_SLOPE * (np.tan(slope_rad)**2)
    
    # Vector Pendiente: El fuego sube (Aspect es cuesta abajo, le sumamos 180)
    up_hill_deg = (aspect_deg + 180) % 360
    up_hill_rad = np.radians(up_hill_deg)
    Sx = Phi_S * np.sin(up_hill_rad)
    Sy = Phi_S * np.cos(up_hill_rad)

    # 4. Factor de Viento (Phi_W)
    # Fórmula empírica: phi_w = c * (vel_kmh)^1.5
    C_WIND = 0.05
    Phi_W = C_WIND * (VIENTO_VEL_KMH ** 1.5)
    
    # Vector Viento: El viento empuja HACA (sumamos 180 a la dirección de origen)
    wind_push_deg = (VIENTO_DIR_GRADOS + 180) % 360
    wind_push_rad = np.radians(wind_push_deg)
    Wx = Phi_W * np.sin(wind_push_rad)
    Wy = Phi_W * np.cos(wind_push_rad)

    print("--- PASO 3: SUMA VECTORIAL Y VELOCIDAD FINAL ---")
    # Sumamos los vectores de empuje
    Push_X = Sx + Wx
    Push_Y = Sy + Wy
    
    # Magnitud total del empuje combinado
    Phi_Total = np.sqrt(Push_X**2 + Push_Y**2)
    
    # ECUACIÓN FINAL DE VELOCIDAD MÁXIMA
    # ROS = R0 * (1 + Phi_Total)
    ROS_max = R0 * (1 + Phi_Total)

    # Mascarar donde no hay combustible o no hay terreno
    ROS_max[combustible == 0] = 0.0
    ROS_max[np.isnan(elevacion)] = 0.0

    print("--- PASO 4: GUARDANDO RESULTADOS ---")
    meta.update(dtype='float32', count=1, nodata=-9999.0)
    with rasterio.open(SALIDA_ROS, 'w', **meta) as dst:
        dst.write(ROS_max.astype('float32'), 1)
        
    print(f"✅ Mapa de velocidades guardado en '{SALIDA_ROS}'")
    print(f"   Velocidad máxima estimada en el mapa: {np.nanmax(ROS_max):.2f} m/min")

    # --- VISUALIZACIÓN DE RESULTADOS ---
    plt.figure(figsize=(15, 6))

    plt.subplot(1, 3, 1)
    plt.imshow(combustible, cmap='tab20', interpolation='none')
    plt.title("Mapa de Combustibles")
    plt.colorbar(shrink=0.5)

    plt.subplot(1, 3, 2)
    plt.imshow(np.degrees(slope_rad), cmap='magma')
    plt.title("Pendiente del Terreno (Grados)")
    plt.colorbar(shrink=0.5)

    plt.subplot(1, 3, 3)
    # Usamos inferno porque los colores de fuego quedan geniales para ROS
    img3 = plt.imshow(ROS_max, cmap='inferno', vmin=0, vmax=np.percentile(ROS_max, 95))
    plt.title(f"Velocidad Máxima (m/min)\nViento: {VIENTO_VEL_KMH}km/h desde {VIENTO_DIR_GRADOS}°")
    plt.colorbar(img3, shrink=0.5)

    plt.tight_layout()
    plt.show()

except Exception as e:
    print(f"❌ Error: {e}")