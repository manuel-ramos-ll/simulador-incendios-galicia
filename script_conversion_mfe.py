import geopandas as gpd
import rasterio
from rasterio import features
import numpy as np
import os

# --- CONFIGURACIÓN DE RUTAS MESTRAS ---
home = os.path.expanduser("~")
# Cambia isto á ruta onde tes o teu .shp en Fedora
ARCHIVO_SHAPEFILE = "mfe_galicia/MFE_11.shp"
# O MDT xigante que acabamos de crear co Script de Python
ARCHIVO_MDT_MESTRE = "MDT_Galicia_25m.tif" 
SALIDA_COMBUSTIBLE = "Combustibles_Galicia_25m.tif"

def obtener_modelo_definitivo(fila):
    """Lóxica intelixente de asignación (A túa función orixinal intacta)"""
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

    if val_original > 0 and val_original <= 13:
        return val_original

    uso = str(fila['UsoMFE'])
    if 'Cultivos' in uso: return 1
    if 'Desarbolado' in uso: return 5
    if 'Arbolado' in uso: return 9
    return 0

try:
    print("--- PASO 1: LER O MOLDE MESTRE (MDT) ---")
    with rasterio.open(ARCHIVO_MDT_MESTRE) as src:
        meta = src.meta.copy()
        shape = src.shape
        transform = src.transform
        crs_objetivo = src.crs

    print("--- PASO 2: PROCESAR O MAPA VECTORIAL DE GALICIA ---")
    print("   Cargando Shapefile (Isto pode tardar un pouco)...")
    gdf = gpd.read_file(ARCHIVO_SHAPEFILE)
    
    if gdf.crs != crs_objetivo:
        print(f"   🔄 Reprojectando coordenadas ao sistema do MDT: {crs_objetivo}...")
        gdf = gdf.to_crs(crs_objetivo)

    print("   Calculating modelos de combustible aplicados á lóxica...")
    gdf['VALOR_FINAL'] = gdf.apply(obtener_modelo_definitivo, axis=1)
    gdf['VALOR_FINAL'] = gdf['VALOR_FINAL'].astype('int16')

    print("\n--- PASO 3: RASTERIZACIÓN TOTAL (MOLDEADO PERFECTO) ---")
    # Xeramos o iterador de xeometrías
    geometrias = ((geom, valor) for geom, valor in zip(gdf.geometry, gdf.VALOR_FINAL))

    # Rasterizamos usando exactamente o tamaño e orientación do MDT mestre
    combustible_array = features.rasterize(
        shapes=geometrias,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype='int16'
    )

    print("--- PASO 4: GARDAR CON COMPRESIÓN ---")
    meta.update(
        dtype='int16', 
        count=1, 
        nodata=0,
        compress='lzw' # Engadimos compresión para que non ocupe gigabytes
    )
    
    with rasterio.open(SALIDA_COMBUSTIBLE, 'w', **meta) as dst:
        dst.write(combustible_array, 1)
        
    print(f"✅ Éxito absoluto! Ficheiro mestre '{SALIDA_COMBUSTIBLE}' xerado.")
    print("Agora as túas dúas matrices son xemelgas idénticas en filas e columnas.")

except Exception as e:
    print(f"❌ Error crítico no procesado: {e}")