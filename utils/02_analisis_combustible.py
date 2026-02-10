import geopandas as gpd
import rasterio
import os

# --- CONFIGURACIÓN ---
# Apuntamos al archivo dentro de la carpeta que mostraste en la imagen
ARCHIVO_SHAPEFILE = "mfe_galicia/MFE_11.shp" 

# Tu archivo del terreno (asegúrate de que el nombre sea exacto)
ARCHIVO_MDT = "terreno.tif"

try:
    print("--- 1. VERIFICACIÓN DE ARCHIVOS ---")
    if not os.path.exists(ARCHIVO_SHAPEFILE):
        print(f"❌ ERROR: No encuentro el archivo en: {ARCHIVO_SHAPEFILE}")
        print("   Asegúrate de que la carpeta 'mfe_galicia' está junto a este script.")
        exit()
    else:
        print(f"✅ Archivo encontrado: {ARCHIVO_SHAPEFILE}")

    print("\n--- 2. CARGANDO DATOS (Esto tardará unos segundos...) ---")
    
    # Leemos solo las primeras 50 filas para no saturar la memoria ahora mismo
    gdf = gpd.read_file(ARCHIVO_SHAPEFILE, rows=50)
    
    # Cargamos el raster para comparar coordenadas
    with rasterio.open(ARCHIVO_MDT) as src:
        crs_raster = src.crs

    print(f"   Sistema Coordenadas Mapa Forestal: {gdf.crs}")
    print(f"   Sistema Coordenadas Terreno:       {crs_raster}")
    
    if str(gdf.crs) == str(crs_raster):
        print("   ✅ ¡Coinciden! No hará falta reproyectar.")
    else:
        print("   ⚠️  Diferentes. Tendremos que convertir el vectorial más adelante.")

    print("\n--- 3. BUSCANDO LA COLUMNA DE VEGETACIÓN ---")
    print("Columnas disponibles:")
    print(gdf.columns.tolist())
    
    print("\n--- 4. MUESTRA DE CONTENIDO ---")
    # Vamos a imprimir las primeras filas para ver qué datos traen
    # Buscamos columnas típicas del MFE
    cols_a_mostrar = [c for c in gdf.columns if 'USO' in c or 'ID' in c or 'CLAVE' in c]
    
    if cols_a_mostrar:
        print(gdf[cols_a_mostrar].head(5))
    else:
        print(gdf.head(5))

except Exception as e:
    print(f"Error crítico: {e}")