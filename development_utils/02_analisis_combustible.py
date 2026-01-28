import geopandas as gpd
import rasterio
import os

''' Ficheiro para análise da información que trae o combustible '''

# --- CONFIGURACIÓN ---

# Ruta do ficheiro do combustible
# ATENCIÓN: Substitúe esta variable polas túas rutas locais absolutas ou relativas
ARCHIVO_SHAPEFILE = "ruta/ao/teu/shapefile/ficheiro.shp" 

# Ruta do terreo
ARCHIVO_MDT = "ruta/aos/teus/ficheiros_tif"

try:
    print("--- 1. VERIFICACIÓN DE ARCHIVOS ---")
    if not os.path.exists(ARCHIVO_SHAPEFILE):
        print(f"❌ ERROR: No se encuentra el archivo en: {ARCHIVO_SHAPEFILE}")
        exit()
    else:
        print(f"✅ Archivo encontrado: {ARCHIVO_SHAPEFILE}")

    print("\n--- 2. CARGANDO DATOS (Esto tardará unos segundos...) ---")
    

    gdf = gpd.read_file(ARCHIVO_SHAPEFILE, rows=50)
    

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
    # Impresión dos datos das primeiras filas 
    cols_a_mostrar = [c for c in gdf.columns if 'USO' in c or 'ID' in c or 'CLAVE' in c]
    
    if cols_a_mostrar:
        print(gdf[cols_a_mostrar].head(5))
    else:
        print(gdf.head(5))

except Exception as e:
    print(f"Error crítico: {e}")