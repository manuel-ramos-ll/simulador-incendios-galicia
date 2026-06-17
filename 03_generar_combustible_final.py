import geopandas as gpd
import rasterio
from rasterio import features
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import box

# --- CONFIGURACIÓN ---
ARCHIVO_SHAPEFILE = "mfe_galicia/MFE_11.shp"
ARCHIVO_MDT = "terreno.tif"
SALIDA_COMBUSTIBLE = "combustible.tif"

def obtener_modelo_definitivo(fila):
    """
    Lógica inteligente para asignar combustible:
    1. Si el mapa ya trae un modelo numérico, úsalo.
    2. Si está vacío, deduce el modelo según el 'UsoMFE'.
    """
    # 1. Intentar leer el ModeloComb original
    val_original = 0
    raw = fila['ModeloComb']
    
    try:
        if isinstance(raw, (int, float)):
            val_original = int(raw)
        elif isinstance(raw, str):
            nums = ''.join(filter(str.isdigit, raw))
            if nums: val_original = int(nums)
    except:
        pass

    # Si encontramos un modelo válido (1-13), lo devolvemos y terminamos
    if val_original > 0 and val_original <= 13:
        return val_original

    # 2. Si no hay modelo, aplicar REGLAS DE PARCHEO según el Uso
    uso = str(fila['UsoMFE']) # Convertir a texto por seguridad
    
    if 'Cultivos' in uso:
        return 1  # Asignamos Pasto Corto (permite paso del fuego)
    
    if 'Desarbolado' in uso:
        return 5  # Asignamos Matorral (Brush)
        
    if 'Arbolado' in uso:
        return 9  # Asignamos Bosque estándar (Hojarasca)
        
    # Artificial, Agua y otros se quedan en 0 (Cortafuegos)
    return 0

try:
    print("--- PASO 1: PREPARAR EL LIENZO (MDT) ---")
    with rasterio.open(ARCHIVO_MDT) as src:
        meta = src.meta.copy()
        shape = src.shape
        transform = src.transform
        crs_objetivo = src.crs
        # Caja para recortar
        bounds = src.bounds
        bbox_terreno = box(bounds.left, bounds.bottom, bounds.right, bounds.top)

    print("--- PASO 2: PROCESAR EL MAPA VECTORIAL ---")
    print("   Cargando Shapefile...")
    gdf = gpd.read_file(ARCHIVO_SHAPEFILE)
    
    if gdf.crs != crs_objetivo:
        print(f"   🔄 Reproyectando coordenadas a {crs_objetivo}...")
        gdf = gdf.to_crs(crs_objetivo)
    
    print("   ✂️  Recortando zona de interés...")
    gdf_recortado = gdf.clip(bbox_terreno)
    
    print(f"   Procesando {len(gdf_recortado)} polígonos...")

    # --- AQUÍ ESTÁ LA MAGIA ---
    # Aplicamos la función fila por fila (axis=1)
    gdf_recortado['VALOR_FINAL'] = gdf_recortado.apply(obtener_modelo_definitivo, axis=1)
    
    # Convertimos a entero pequeño para ahorrar memoria
    gdf_recortado['VALOR_FINAL'] = gdf_recortado['VALOR_FINAL'].astype('int16')

    print("\n--- PASO 3: RASTERIZACIÓN ---")
    # Generamos pares (Geometría, Valor)
    geometrias = ((geom, valor) for geom, valor in zip(gdf_recortado.geometry, gdf_recortado.VALOR_FINAL))

    combustible_array = features.rasterize(
        shapes=geometrias,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype='int16'
    )

    print("--- PASO 4: GUARDAR Y VISUALIZAR ---")
    meta.update(dtype='int16', count=1, nodata=0)
    
    with rasterio.open(SALIDA_COMBUSTIBLE, 'w', **meta) as dst:
        dst.write(combustible_array, 1)
        
    print(f"✅ Archivo '{SALIDA_COMBUSTIBLE}' generado correctamente.")

    # Visualización comparativa
    plt.figure(figsize=(12, 6))
    
    # Mapa de colores personalizado para distinguir tipos
    # 0=Negro (Carretera), 1=VerdeClaro (Cultivo), 9=VerdeOscuro (Bosque)
    cmap = plt.cm.get_cmap('tab20c', 14) 
    
    plt.imshow(combustible_array, cmap=cmap, vmin=0, vmax=13, interpolation='nearest')
    plt.colorbar(label='Modelo Combustible (1=Pasto, 0=Carretera/Agua)')
    plt.title("Mapa de Combustible")
    plt.show()

except Exception as e:
    print(f"❌ Error: {e}")