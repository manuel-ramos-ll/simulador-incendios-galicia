import streamlit as st
import rasterio
import numpy as np
import requests
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
from skimage.graph import MCP_Geometric
from streamlit_folium import st_folium
import folium
from folium import Icon
from pyproj import Transformer

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Simulador de Incendios - MeteoGalicia v5", layout="wide")

# Inicialización del estado de la sesión para el marcador del mapa
if 'foco_ignicion' not in st.session_state:
    st.session_state['foco_ignicion'] = None 

# --- 2. FUNCIONES LÓGICAS (Meteorología y Física) ---

def consultar_viento_api(api_key, bounds, crs_raster):
    """Obtiene y procesa el viento desde la API v5 aplicando transformaciones topológicas"""
    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    lon_min, lat_min = transformer_to_wgs84.transform(bounds.left, bounds.bottom)
    lon_max, lat_max = transformer_to_wgs84.transform(bounds.right, bounds.top)

    n_puntos = 4 
    lons = np.linspace(lon_min, lon_max, n_puntos)
    lats = np.linspace(lat_min, lat_max, n_puntos)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    
    puntos_coords = [f"{lon:.4f},{lat:.4f}" for lon, lat in zip(grid_lon.flatten(), grid_lat.flatten())]
    coords_str = ";".join(puntos_coords)

    url = "https://servizos.meteogalicia.gal/apiv5/getNumericForecastInfo"
    params = {
        "coords": coords_str,
        "variables": "wind",
        "models": "WRF",
        "format": "application/json",
        "API_KEY": api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
    except Exception as e:
        return None, f"Error de conexión con la API: {e}"

    if "exception" in data:
        return None, f"Error API: {data['exception']['message']}"
    
    puntos_u, puntos_v, puntos_pos = [], [], []
    transformer_to_utm = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)

    for feature in data['features']:
        if "exception" in feature: continue
        try:
            v_val = feature['properties']['days'][0]['variables'][0]['values'][0]
            vel, direccion = v_val['moduleValue'], v_val['directionValue']
            lon_wgs, lat_wgs = feature['geometry']['coordinates']
            
            x_utm, y_utm = transformer_to_utm.transform(lon_wgs, lat_wgs)
            
            # Vector de empuje (+180º)
            rad = np.radians((direccion + 180) % 360)
            puntos_u.append(vel * np.sin(rad))
            puntos_v.append(vel * np.cos(rad))
            puntos_pos.append((x_utm, y_utm))
        except (KeyError, IndexError):
            continue
    
    return (np.array(puntos_pos), puntos_u, puntos_v), None

# --- 3. INTERFAZ DE USUARIO (Sidebar) ---

st.title("🔥 Simulador Dinámico de Propagación de Incendios")
st.markdown("Cálculo baseado no modelo físico de **Rothermel** e datos en tempo real de **MeteoGalicia (WRF)**")

with st.sidebar:
    st.header("Configuración Principal")
    api_key = st.text_input("MeteoSIX API KEY", type="password", help="Introduce a túa chave da API de MeteoGalicia")
    
    horas_sim = st.slider("Horizonte de simulación (horas)", 1, 12, 6)
    
    # 🔴 TODO O TÉCNICO VAI AQUÍ DENTRO (Oculto por defecto)
    with st.expander("⚙️ Configuración Avanzada"):
        st.caption("Arquivos base e parámetros do motor físico")
        
        uploaded_mdt = st.file_uploader("Modelo Topográfico (.tif)", type=["tif"])
        uploaded_fuel = st.file_uploader("Mapa de Combustibles (.tif)", type=["tif"])
        
        st.divider() # Engadimos unha liña separadora visual
        
        sigma_blur = st.slider("Suavizado de vento (Sigma)", 1, 5, 3)
        c_wind = st.number_input("Factor de influencia do vento", 0.01, 0.10, 0.05)

    # Botón inferior para limpar
    st.write("") # Espazo en branco
    if st.button("🔄 Limpar punto de ignición", use_container_width=True):
        st.session_state['foco_ignicion'] = None
        st.rerun()

# --- 4. SELECCIÓN DE IGNICIÓN (MAPA BLOQUEADO A GALICIA) ---
st.subheader("1. Selecciona el foco de ignición en el mapa")

# Límites de Galicia
min_lat, max_lat = 41.8, 43.9
min_lon, max_lon = -9.4, -6.7

map_center = [42.8, -7.9]
map_zoom = 8

if st.session_state['foco_ignicion']:
    map_center = st.session_state['foco_ignicion']
    map_zoom = 11

m = folium.Map(
    location=map_center, 
    zoom_start=map_zoom,
    min_zoom=8,
    min_lat=min_lat, max_lat=max_lat,
    min_lon=min_lon, max_lon=max_lon,
    max_bounds=True
)

if st.session_state['foco_ignicion']:
    folium.Marker(
        location=st.session_state['foco_ignicion'],
        popup="Punto de Ignición",
        icon=Icon(color='red', icon='fire', prefix='fa')
    ).add_to(m)

# Mapa más cuadrado y centrado
mapa_data = st_folium(m, height=450, width=600, key="mapa_galicia")

# Lógica de captura de clic
if mapa_data["last_clicked"]:
    clicked_coords = (mapa_data["last_clicked"]["lat"], mapa_data["last_clicked"]["lng"])
    if clicked_coords != st.session_state['foco_ignicion']:
        st.session_state['foco_ignicion'] = clicked_coords
        st.rerun()

ignicion_coords = st.session_state['foco_ignicion']

if ignicion_coords:
    st.success(f"📍 Punto seleccionado: Lat {ignicion_coords[0]:.4f}, Lon {ignicion_coords[1]:.4f}")
else:
    st.info("Haz clic en el mapa para establecer el inicio del fuego.")

# --- 5. EJECUCIÓN ---
if st.button("🚀 Iniciar Simulación", type="primary"):
    if not api_key:
        st.error("⚠️ Introduce tu API KEY en el panel izquierdo.")
    elif not uploaded_mdt or not uploaded_fuel:
        st.error("⚠️ Debes subir ambos archivos (.tif) para continuar.")
    elif not ignicion_coords:
        st.error("⚠️ Selecciona un punto en el mapa.")
    else:
        with st.spinner("Procesando física de propagación y meteorología..."):
            try:
                # Carga de archivos directamente desde el uploader
                with rasterio.open(uploaded_mdt) as src:
                    elev = src.read(1).astype(float)
                    elev[elev == src.nodata] = np.nan
                    bounds = src.bounds
                    rows, cols = elev.shape
                    cell_size = src.transform[0]
                    crs_raster = src.crs
                    
                    # Convertir Clic (WGS84) a Píxel (UTM)
                    trans_click = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)
                    x_click, y_click = trans_click.transform(ignicion_coords[1], ignicion_coords[0])
                    py, px = src.index(x_click, y_click)
                    
                    if py < 0 or py >= rows or px < 0 or px >= cols:
                        st.error("❌ El punto seleccionado está fuera de los límites del terreno subido.")
                        st.stop()

                with rasterio.open(uploaded_fuel) as src_f:
                    fuel = src_f.read(1)

                # Meteorología
                viento_data, error = consultar_viento_api(api_key, bounds, crs_raster)
                if error:
                    st.error(error); st.stop()
                
                pos, u_pts, v_pts = viento_data
                target_x = np.linspace(bounds.left, bounds.right, cols)
                target_y = np.linspace(bounds.top, bounds.bottom, rows)
                t_x_grid, t_y_grid = np.meshgrid(target_x, target_y)
                
                # Interpolación y Suavizado
                U_interp = griddata(pos, u_pts, (t_x_grid, t_y_grid), method='cubic')
                V_interp = griddata(pos, v_pts, (t_x_grid, t_y_grid), method='cubic')
                U_interp = np.where(np.isnan(U_interp), np.nanmean(U_interp), U_interp)
                V_interp = np.where(np.isnan(V_interp), np.nanmean(V_interp), V_interp)
                
                U_viento = gaussian_filter(U_interp, sigma=sigma_blur)
                V_viento = gaussian_filter(V_interp, sigma=sigma_blur)

                # Física de Rothermel
                dy, dx = np.gradient(elev, cell_size)
                slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
                aspect_rad = np.arctan2(-dx, dy)
                
                Phi_S = 5.275 * (np.tan(slope_rad)**2)
                Sx, Sy = Phi_S * np.sin(aspect_rad + np.pi), Phi_S * np.cos(aspect_rad + np.pi)
                
                # Modelos de Anderson
                VALORES_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
                R0 = np.zeros_like(fuel, dtype=float)
                for m, v in VALORES_R0.items(): R0[fuel == m] = v
                
                Push_X, Push_Y = Sx + (c_wind * U_viento), Sy + (c_wind * V_viento)
                ros_max = R0 * (1 + np.sqrt(Push_X**2 + Push_Y**2))

                # Motor de Isocronas
                cost_matrix = np.full_like(ros_max, np.inf, dtype=np.float32)
                burnable = ros_max > 0.01
                cost_matrix[burnable] = cell_size / ros_max[burnable]

                mcp = MCP_Geometric(cost_matrix)
                tiempos, _ = mcp.find_costs(starts=[(py, px)])
                tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
                tiempos[tiempos > (horas_sim * 60)] = np.nan 

                # Visualización
                st.subheader("2. Resultados de la Simulación Espacial")
                fig, ax = plt.subplots(figsize=(12, 10))
                ax.imshow(elev, cmap='terrain', alpha=0.6)
                ax.plot(px, py, 'b*', markersize=15, label="Ignición")
                
                max_mins = np.nanmax(tiempos)
                if max_mins > 0:
                    step = 60 if max_mins > 120 else 15
                    niveles = np.arange(step, max_mins, step)
                    if len(niveles) > 0:
                        contour = ax.contour(tiempos, levels=niveles, colors='red', linewidths=1.2)
                        ax.clabel(contour, inline=True, fontsize=9, fmt='%1.0f min')
                
                im = ax.imshow(np.ma.masked_invalid(tiempos), cmap='YlOrRd', alpha=0.5)
                plt.colorbar(im, ax=ax, label="Minutos desde ignición")
                ax.set_axis_off()
                st.pyplot(fig)
                st.success("✅ Simulación finalizada.")

            except Exception as e:
                st.error(f"❌ Error crítico: {e}")