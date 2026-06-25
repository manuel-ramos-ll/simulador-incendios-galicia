import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio import features

''' Ficheiro para xerar a matriz de modelos de combustible baseada no MDT '''

# --- 1. CONFIGURACIÓN DE RUTAS ---
# ATENCIÓN: Substitúe estas variables polas túas rutas locais absolutas ou relativas
ARCHIVO_SHAPEFILE = "ruta/ao/teu/shapefile/MFE_11.shp"
ARCHIVO_MDT_MESTRE = "ruta/ao/teu/MDT_Galicia_25m.tif" 

# Nome do ficheiro final resultante
SALIDA_COMBUSTIBLE = "Combustibles_Galicia_25m.tif"

def obtener_modelo_definitivo(fila):
    """Lóxica intelixente de asignación de modelos de combustible de Rothermel."""
    val_original = 0
    raw = fila['ModeloComb']
    
    try:
        if isinstance(raw, (int, float)):
            val_original = int(raw)
        elif isinstance(raw, str):
            nums = ''.join(filter(str.isdigit, raw))
            if nums: 
                val_original = int(nums)
    except Exception:
        pass

    # Se o valor é un modelo válido (1-13 de Rothermel), mantémolo
    if 0 < val_original <= 13:
        return val_original

    # Lóxica de respaldo baseada no Uso
    uso = str(fila['UsoMFE'])
    if 'Cultivos' in uso: return 1
    if 'Desarbolado' in uso: return 5
    if 'Arbolado' in uso: return 9
    return 0

def main():
    if ARCHIVO_SHAPEFILE == "ruta/ao/teu/shapefile/MFE_11.shp" or ARCHIVO_MDT_MESTRE == "ruta/ao/teu/MDT_Galicia_25m.tif":
        print("❌ Erro: Debes configurar as rutas 'ARCHIVO_SHAPEFILE' e 'ARCHIVO_MDT_MESTRE' antes de executar o script.")
        return
        
    if not os.path.exists(ARCHIVO_SHAPEFILE):
        print(f"❌ Erro: Non se atopa o Shapefile na ruta: {ARCHIVO_SHAPEFILE}")
        return
        
    if not os.path.exists(ARCHIVO_MDT_MESTRE):
        print(f"❌ Erro: Non se atopa o MDT mestre na ruta: {ARCHIVO_MDT_MESTRE}")
        return

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
            print(f" Reproxección das coordenadas ao sistema do MDT: {crs_objetivo}...")
            gdf = gdf.to_crs(crs_objetivo)

        print("   Calculando modelos de combustible aplicados á lóxica...")
        gdf['VALOR_FINAL'] = gdf.apply(obtener_modelo_definitivo, axis=1)
        gdf['VALOR_FINAL'] = gdf['VALOR_FINAL'].astype('int16')

        print("\n--- PASO 3: RASTERIZACIÓN TOTAL ---")
        geometrias = ((geom, valor) for geom, valor in zip(gdf.geometry, gdf.VALOR_FINAL))

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
            compress='lzw' 
        )
        
        with rasterio.open(SALIDA_COMBUSTIBLE, 'w', **meta) as dst:
            dst.write(combustible_array, 1)
            
        print(f"Éxito! Ficheiro '{SALIDA_COMBUSTIBLE}' xerado en {os.getcwd()}.")

    except Exception as e:
        print(f"Erro crítico no procesado: {e}")

if __name__ == "__main__":
    main()