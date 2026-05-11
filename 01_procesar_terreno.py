import rasterio
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def calcular_pendiente_orientacion(dem, cell_size):
    """Calcula pendiente y orientación"""
    dy, dx = np.gradient(dem, cell_size)
    
    pendiente_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    pendiente_deg = np.degrees(pendiente_rad)
    
    orientacion_rad = np.arctan2(-dx, dy)
    orientacion_deg = (np.degrees(orientacion_rad) + 360) % 360

    return pendiente_deg, orientacion_deg

# --- CONFIGURACIÓN ---
ARCHIVO_MDT = "terreno.tif" 

try:
    print(f"Abriendo {ARCHIVO_MDT}...")
    with rasterio.open(ARCHIVO_MDT) as src:
        elevacion = src.read(1)
        # Manejo de valores nulos para que no salgan picos raros
        elevacion = np.where(elevacion == src.nodata, np.nan, elevacion)
        
        transform = src.transform
        cell_size = transform[0]
        
    print("Calculando variables del terreno...")
    pendiente, orientacion = calcular_pendiente_orientacion(elevacion, cell_size)

    # --- VISUALIZACIÓN ---
    print("Generando gráficos (esto puede tardar unos segundos)...")
    
    # Creamos una figura con 4 huecos (2 filas x 2 columnas)
    fig = plt.figure(figsize=(16, 10))

    # 1. Mapa de Elevación (2D)
    ax1 = fig.add_subplot(2, 2, 1)
    im1 = ax1.imshow(elevacion, cmap='terrain')
    ax1.set_title("Elevación (m)")
    plt.colorbar(im1, ax=ax1)

    # 2. Mapa de Pendiente (2D)
    ax2 = fig.add_subplot(2, 2, 2)
    im2 = ax2.imshow(pendiente, cmap='magma')
    ax2.set_title("Pendiente (Grados) - Clave para velocidad")
    plt.colorbar(im2, ax=ax2)

    # 3. Mapa de Orientación (2D)
    ax3 = fig.add_subplot(2, 2, 3)
    im3 = ax3.imshow(orientacion, cmap='hsv')
    ax3.set_title("Orientación (Grados)")
    plt.colorbar(im3, ax=ax3)

    # 4. VISUALIZACIÓN 3D
    print("Renderizando modelo 3D...")
    ax4 = fig.add_subplot(2, 2, 4, projection='3d')

    # Crear malla de coordenadas X, Y
    rows, cols = elevacion.shape
    x = np.arange(0, cols)
    y = np.arange(0, rows)
    X, Y = np.meshgrid(x, y)

    # FACTOR DE "DIEZMADO" (Downsampling)
    # Si stride = 1, pinta todos los píxeles (muy lento).
    # Si stride = 10, pinta 1 de cada 10 píxeles (rápido).
    stride = 5 
    
    # Pintamos la superficie
    surf = ax4.plot_surface(
        X[::stride, ::stride], 
        Y[::stride, ::stride], 
        elevacion[::stride, ::stride], 
        cmap='terrain', 
        linewidth=0, 
        antialiased=False
    )
    
    # Ajustes del gráfico 3D
    ax4.set_title("Relieve 3D")
    ax4.set_zlabel('Altitud (m)')
    
    # Cambiar el ángulo de vista inicial
    ax4.view_init(elev=45, azim=135) 
    
    # Añadir barra de color
    fig.colorbar(surf, ax=ax4, shrink=0.5, aspect=10)

    plt.tight_layout()
    plt.show()
    print("Hecho.")

except Exception as e:
    print(f"Error: {e}")