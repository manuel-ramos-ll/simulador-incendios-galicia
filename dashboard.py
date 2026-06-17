import streamlit as st
import rasterio
import numpy as np
import requests
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from skimage.graph import MCP_Geometric
from streamlit_folium import st_folium
import folium

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador de Incendios - MeteoGalicia v5", layout="wide")

# --- 2. FUNCIONES LÓGICAS (Basadas en tus Scripts 4 y 5) ---

def consultar_viento_api(api_key, bounds):
    """Obtiene y procesa el viento desde la API v5 [cite: 53, 143, 153]"""
    n_puntos = 4 
    lons = np.linspace(bounds.left, bounds.right, n_puntos)
    lats = np.linspace(bounds.bottom, bounds.top, n_puntos)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    
    puntos_coords = [f"{lon},{lat}" for lon, lat in zip(grid_lon.flatten(), grid_lat.flatten())]
    coords_str = ";".join(puntos_coords)

    url = "https://servizos.meteogalicia.gal/apiv5/getNumericForecastInfo"
    params = {
        "coords": coords_str,
        "variables": "wind",
        "models": "WRF",
        "format": "application/json",
        "API_KEY": api_key
    }

    response = requests.get(url, params=params)
    data = response.json()

    # Gestión de errores según manual [cite: 426, 617, 2055]
    if "exception" in data:
        return None, f"Error {data['exception']['code']}: {data['exception']['message']}"
    
    puntos_u, puntos_v, puntos_pos = [], [], []
    for feature in data['features']:
        if "exception" in feature: continue
        # Extraer velocidad y dirección [cite: 1403, 1404]
        v_val = feature['properties']['days'][0]['variables'][0]['values'][0]
        vel, direccion = v_val['moduleValue'], v_val['directionValue']
        lon, lat = feature['geometry']['coordinates'] # [cite: 238]
        
        rad = np.radians((direccion + 180) % 360)
        puntos_u.append(vel * np.sin(rad))
        puntos_v.append(vel * np.cos(rad))
        puntos_pos.append((lon, lat))
    
    return (np.array(puntos_pos), puntos_u, puntos_v), None

# --- 3. INTERFAZ DE USUARIO ---

st.title("🔥 Simulador de Propagación de Incendios")
st.markdown("Cálculo dinámico basado en topografía y viento de **MeteoGalicia v5**")

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("MeteoSIX API KEY", type="password")
    
    st.subheader("Archivos de Entrada")
    archivo_mdt = st.text_input("Ruta MDT (.tif)", "terreno_galicia.tif")
    archivo_fuel = st.text_input("Ruta Combustible (.tif)", "combustible_galicia.tif")
    
    horas_sim = st.slider("Horizonte de simulación (horas)", 1, 12, 6)

# --- 4. SELECCIÓN DE IGNICIÓN (MAPA) ---
st.subheader("1. Selecciona el punto de ignición en el mapa")
# Coordenadas aproximadas de Galicia para centrar
m = folium.Map(location=[42.8, -8.0], zoom_start=8)
mapa_data = st_folium(m, height=400, width=800)

ignicion_coords = None
if mapa_data["last_clicked"]:
    ignicion_coords = (mapa_data["last_clicked"]["lat"], mapa_data["last_clicked"]["lng"])
    st.success(f"📍 Punto de ignición seleccionado: {ignicion_coords}")

# --- 5. EJECUCIÓN ---
if st.button("🚀 Iniciar Simulación"):
    if not api_key or not ignicion_coords:
        st.error("Por favor, introduce tu API KEY y selecciona un punto en el mapa.")
    else:
        with st.spinner("Procesando datos xeoespaciais y consultando MeteoGalicia..."):
            try:
                # --- FASE 4: METEOROLOGÍA Y ROS ---
                with rasterio.open(archivo_mdt) as src:
                    elev = src.read(1)
                    meta = src.meta
                    bounds = src.bounds
                    rows, cols = elev.shape
                    cell_size = src.transform[0]
                    # Transformar coordenadas click a píxel
                    py, px = src.index(ignicion_coords[1], ignicion_coords[0])

                with rasterio.open(archivo_fuel) as src_f:
                    fuel = src_f.read(1)

                # Consultar API [cite: 143, 153]
                viento_data, error = consultar_viento_api(api_key, bounds)
                if error:
                    st.error(error)
                    st.stop()
                
                pos, u_pts, v_pts = viento_data
                
                # Interpolación
                target_lons = np.linspace(bounds.left, bounds.right, cols)
                target_lats = np.linspace(bounds.top, bounds.bottom, rows)
                t_lon_grid, t_lat_grid = np.meshgrid(target_lons, target_lats)
                
                U_viento = griddata(pos, u_pts, (t_lon_grid, t_lat_grid), method='linear')
                V_viento = griddata(pos, v_pts, (t_lon_grid, t_lat_grid), method='linear')

                # Cálculo de ROS (Física del Script 4)
                dy, dx = np.gradient(elev, cell_size)
                slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
                aspect_rad = np.arctan2(-dx, dy)
                
                C_SLOPE = 5.275
                Phi_S = C_SLOPE * (np.tan(slope_rad)**2)
                Sx, Sy = Phi_S * np.sin(aspect_rad + np.pi), Phi_S * np.cos(aspect_rad + np.pi)
                
                VALORES_R0 = {0:0, 1:15, 4:25, 9:3.5} # Simplificado
                R0 = np.vectorize(lambda x: VALORES_R0.get(x, 5.0))(fuel)
                
                C_WIND = 0.05
                Push_X, Push_Y = Sx + (C_WIND * U_viento), Sy + (C_WIND * V_viento)
                ros_max = R0 * (1 + np.sqrt(Push_X**2 + Push_Y**2))

                # --- FASE 5: PROPAGACIÓN (Script 5) ---
                cost_matrix = np.full_like(ros_max, np.inf)
                burnable = ros_max > 0.01
                cost_matrix[burnable] = cell_size / ros_max[burnable]

                mcp = MCP_Geometric(cost_matrix)
                tiempos, _ = mcp.find_costs(starts=[(py, px)])
                tiempos[tiempos > (horas_sim * 60)] = np.nan # Limitar al tiempo pedido

                # --- VISUALIZACIÓN ---
                st.subheader("2. Resultados de la Simulación")
                fig, ax = plt.subplots(figsize=(10, 8))
                ax.imshow(elev, cmap='terrain', alpha=0.6)
                ax.plot(px, py, 'r*', markersize=15, label="Ignición")
                
                tiempo_masked = np.ma.masked_invalid(tiempos)
                im = ax.imshow(tiempo_masked, cmap='YlOrRd', alpha=0.5)
                plt.colorbar(im, label="Minutos desde ignición")
                
                st.pyplot(fig)
                st.success("✅ Simulación finalizada correctamente.")

            except Exception as e:
                st.error(f"Error durante la ejecución: {e}")