import os
import glob
import rasterio
from rasterio.merge import merge

# 1. Configuración de rutas (Máis robusto para Linux)
home = os.path.expanduser("~")
# Proba con "Descargas" ou "Downloads" dependendo de como estea o teu sistema
cartafol_tifs = os.path.join(home, "Descargas/mdt_Galicia/mapas_descargados_manuel") 

# Se non existe Descargas, probamos con Downloads
if not os.path.exists(cartafol_tifs):
    cartafol_tifs = os.path.join(home, "Downloads")

ficheiro_saida = "MDT_Galicia_25m.tif"

# 2. Procurar todos os .tif
search_path = os.path.join(cartafol_tifs, "*.tif")
files_to_mosaic = glob.glob(search_path)

if len(files_to_mosaic) == 0:
    print(f"❌ Erro: Non se atoparon ficheiros .tif en {cartafol_tifs}")
else:
    print(f"✅ Atopados {len(files_to_mosaic)} ficheiros. Iniciando unión...")

    # 3. Abrir ficheiros
    src_files_to_mosaic = [rasterio.open(f) for f in files_to_mosaic]

    # 4. Fusionar (Merge)
    mosaic, out_trans = merge(src_files_to_mosaic)

    # 5. Configurar metadatos con compresión LZW
    out_meta = src_files_to_mosaic[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans,
        "compress": "lzw",
        "dtype": "float32"
    })

    # 6. Gardar
    with rasterio.open(ficheiro_saida, "w", **out_meta) as dest:
        dest.write(mosaic)

    # Pechar recursos
    for src in src_files_to_mosaic:
        src.close()

    print(f"🎉 Éxito! O ficheiro '{ficheiro_saida}' está listo en: {os.getcwd()}")