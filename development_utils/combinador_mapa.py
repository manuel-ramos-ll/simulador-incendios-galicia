import os
import glob
import rasterio
from rasterio.merge import merge

''' Ficheiro para combinar todos os ficheiros .tif do MDT nun só mosaico '''

# --- 1. CONFIGURACIÓN DE RUTAS ---
#  ATENCIÓN : Substitúe esta variable polo cartafol onde teñas descargados os teus ficheiros .tif
CARTAFOL_TIFS = "ruta/aos/teus/ficheiros_tif" 

# Nome do ficheiro final unificado
FICHEIRO_SAIDA = "MDT_Galicia_25m.tif"

def main():
    if CARTAFOL_TIFS == "ruta/aos/teus/ficheiros_tif":
        print("❌ Erro: Debes configurar a variable 'CARTAFOL_TIFS' coa túa ruta local antes de executar o script.")
        return

    if not os.path.exists(CARTAFOL_TIFS):
        print(f"❌ Erro: O cartafol '{CARTAFOL_TIFS}' non existe. Comproba a ruta especificada.")
        return

    # --- 2. PROCURAR TODOS OS FICHEIROS .TIF ---
    search_path = os.path.join(CARTAFOL_TIFS, "*.tif")
    files_to_mosaic = glob.glob(search_path)

    if len(files_to_mosaic) == 0:
        print(f"❌ Erro: Non se atoparon ficheiros .tif en '{CARTAFOL_TIFS}'.")
        return
        
    print(f" Atopados {len(files_to_mosaic)} ficheiros. Iniciando unión...")

    # --- 3. ABRIR FICHEIROS ---
    src_files_to_mosaic = [rasterio.open(f) for f in files_to_mosaic]

    try:
        # --- 4. FUSIONAR (MERGE) ---
        mosaic, out_trans = merge(src_files_to_mosaic)

        # --- 5. CONFIGURAR METADATOS E COMPRESIÓN ---
        out_meta = src_files_to_mosaic[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans,
            "compress": "lzw",
            "dtype": "float32"
        })

        # --- 6. GARDAR O RESULTADO ---
        with rasterio.open(FICHEIRO_SAIDA, "w", **out_meta) as dest:
            dest.write(mosaic)

        print(f"O ficheiro '{FICHEIRO_SAIDA}' está listo en: {os.getcwd()}")

    finally:
        # --- 7. PECHAR RECURSOS DE FORMA SEGURA ---
        for src in src_files_to_mosaic:
            src.close()

if __name__ == "__main__":
    main()