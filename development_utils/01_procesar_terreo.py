import rasterio
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

''' Ficheiro para análise e visualización do terreo '''

def calcular_pendente_orientacion(dem, cell_size):
    """Calcula pendente e orientación"""
    dy, dx = np.gradient(dem, cell_size)
    
    pendente_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    pendente_deg = np.degrees(pendente_rad)
    
    orientacion_rad = np.arctan2(-dx, dy)
    orientacion_deg = (np.degrees(orientacion_rad) + 360) % 360

    return pendente_deg, orientacion_deg

# --- CONFIGURACIÓN ---
# ATENCIÓN: Substitúe esta variable polas túas rutas locais absolutas ou relativas
ARCHIVO_MDT = "ruta/aos/teus/ficheiros_tif"

try:
    print(f"Abrindo {ARCHIVO_MDT}...")
    with rasterio.open(ARCHIVO_MDT) as src:
        elevacion = src.read(1)
        # Xestión valores nulos
        elevacion = np.where(elevacion == src.nodata, np.nan, elevacion)
        
        transform = src.transform
        cell_size = transform[0]
        
    print("Calculando variables do terreo...")
    pendente, orientacion = calcular_pendente_orientacion(elevacion, cell_size)

    # --- VISUALIZACIÓN ---
    print("Xerando gráficos (isto pode tardar uns segundos)...")
    
    fig = plt.figure(figsize=(16, 10))

    # 1. Mapa de Elevación (2D)
    ax1 = fig.add_subplot(2, 2, 1)
    im1 = ax1.imshow(elevacion, cmap='terrain')
    ax1.set_title("Elevación (m)")
    plt.colorbar(im1, ax=ax1)

    # 2. Mapa de Pendente (2D)
    ax2 = fig.add_subplot(2, 2, 2)
    im2 = ax2.imshow(pendente, cmap='magma')
    ax2.set_title("Pendente (Grados) - Clave para velocidade")
    plt.colorbar(im2, ax=ax2)

    # 3. Mapa de Orientación (2D)
    ax3 = fig.add_subplot(2, 2, 3)
    im3 = ax3.imshow(orientacion, cmap='hsv')
    ax3.set_title("Orientación (Grados)")
    plt.colorbar(im3, ax=ax3)

    # 4. VISUALIZACIÓN 3D
    print("Renderizando modelo 3D...")
    ax4 = fig.add_subplot(2, 2, 4, projection='3d')

    rows, cols = elevacion.shape
    x = np.arange(0, cols)
    y = np.arange(0, rows)
    X, Y = np.meshgrid(x, y)

    # FACTOR DE DIEZMADO
    stride = 5 
    
    surf = ax4.plot_surface(
        X[::stride, ::stride], 
        Y[::stride, ::stride], 
        elevacion[::stride, ::stride], 
        cmap='terrain', 
        linewidth=0, 
        antialiased=False
    )
    
    ax4.set_title("Relieve 3D")
    ax4.set_zlabel('Altitud (m)')
    ax4.view_init(elev=45, azim=135) 
    
    fig.colorbar(surf, ax=ax4, shrink=0.5, aspect=10)

    plt.tight_layout()
    plt.show()
    print("Hecho.")

except Exception as e:
    print(f"Error: {e}")