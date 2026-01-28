import rasterio
import numpy as np
import matplotlib.pyplot as plt

def calcular_pendiente_orientacion(dem, cell_size):
    """
    Calcula pendiente (grados) y orientación (grados) a partir de una matriz de elevación.
    Usamos el método de gradiente de NumPy.
    """
    # dy, dx son los gradientes (cambio de altura por celda)
    dy, dx = np.gradient(dem, cell_size)

    # Cálculo de la pendiente (Slope)
    # Pitágoras: la hipotenusa del cambio en x e y
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    slope_deg = np.degrees(slope_rad)

    # Cálculo de la orientación (Aspect)
    # 0=Norte, 90=Este, 180=Sur, 270=Oeste
    aspect_rad = np.arctan2(-dx, dy) # Signos ajustados para convención geográfica
    aspect_deg = np.degrees(aspect_rad)
    
    # Convertir a 0-360 grados (el arctan2 devuelve -180 a 180)
    aspect_deg = (aspect_deg + 360) % 360

    return slope_deg, aspect_deg

# --- CONFIGURACIÓN ---
# CAMBIA ESTO por el nombre de tu archivo descargado del IGN
ARCHIVO_MDT = "terreno.tif" 

try:
    print(f"Abriendo {ARCHIVO_MDT}...")
    with rasterio.open(ARCHIVO_MDT) as src:
        # 1. Leer la matriz de elevación (banda 1)
        elevacion = src.read(1)
        
        # Leer metadatos importantes
        profile = src.profile
        transform = src.transform
        cell_size = transform[0] # Tamaño del píxel en metros (ej. 5m o 25m)
        
        # Manejar valores nulos (NoData) si existen
        if src.nodata is not None:
            elevacion = np.ma.masked_equal(elevacion, src.nodata)

    print(f"Dimensiones del mapa: {elevacion.shape}")
    print(f"Resolución de celda: {cell_size} metros")

    # 2. Calcular variables físicas
    print("Calculando pendientes y orientaciones...")
    pendiente, orientacion = calcular_pendiente_orientacion(elevacion, cell_size)

    # 3. Visualización
    print("Generando gráficos...")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Mapa de Elevación
    im1 = axes[0].imshow(elevacion, cmap='terrain')
    axes[0].set_title("Elevación (m)")
    plt.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04)

    # Mapa de Pendiente
    im2 = axes[1].imshow(pendiente, cmap='magma') # Magma es bueno para intensidad
    axes[1].set_title("Pendiente (Grados)")
    plt.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04)

    # Mapa de Orientación
    im3 = axes[2].imshow(orientacion, cmap='hsv') # HSV es cíclico (bueno para ángulos)
    axes[2].set_title("Orientación (Grados)")
    plt.colorbar(im3, ax=axes[2], fraction=0.046, pad=0.04)

    plt.tight_layout()
    plt.show()
    
    print("¡Éxito! Tienes las matrices base para el simulador.")

except FileNotFoundError:
    print(f"ERROR: No encuentro el archivo '{ARCHIVO_MDT}'.")
    print("Por favor, descarga un MDT del CNIG y ponlo en esta carpeta.")
except Exception as e:
    print(f"Ocurrió un error inesperado: {e}")