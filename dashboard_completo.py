import streamlit as st
import rasterio
from rasterio.windows import from_bounds
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
import os
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import streamlit.components.v1 as components
from skimage import measure
import streamlit.components.v1 as components

# --- 1. CONFIGURACIÓN DE PÁGINA E RUTAS ---
st.set_page_config(page_title="Simulador de Incendios - MeteoGalicia v5", layout="wide")

# Asegúrate de que estes nomes coinciden cos teus ficheiros na mesma carpeta do script
FICHEIRO_MDT = "MDT_Galicia_25m.tif"
FICHEIRO_COMBUSTIBLE = "Combustibles_Galicia_25m.tif" 

# Tamaño do cadrado de simulación (en metros). 10000m = 10x10 km de radio arredor do clic
RADIO_SIMULACION_METROS = 5000 

if 'foco_ignicion' not in st.session_state:
    st.session_state['foco_ignicion'] = None 

# --- 2. FUNCIONES LÓGICAS (Meteorología) ---
def consultar_viento_api(api_key, bounds, crs_raster):
    """Obtén e procesa o vento desde a API v5 aplicando transformacións topolóxicas"""
    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    
    # 🌟 CORRECCIÓN: Detectar se é unha tupla normal ou un obxecto BoundingBox
    if hasattr(bounds, 'left'):
        left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
    else:
        left, bottom, right, top = bounds  # Desempaquetado directo se é unha tupla

    lon_min, lat_min = transformer_to_wgs84.transform(left, bottom)
    lon_max, lat_max = transformer_to_wgs84.transform(right, top)

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
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
    except Exception as e:
        return None, f"Error de conexión coa API: {e}"

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
            
            rad = np.radians((direccion + 180) % 360)
            puntos_u.append(vel * np.sin(rad))
            puntos_v.append(vel * np.cos(rad))
            puntos_pos.append((x_utm, y_utm))
        except (KeyError, IndexError):
            continue
    
    return (np.array(puntos_pos), puntos_u, puntos_v), None

# --- 3. INTERFAZ DE USUARIO (Sidebar) ---
st.title("🔥 Simulador Automático de Propagación de Incendios (Galicia)")
st.markdown("Cálculo baseado no modelo físico de **Rothermel** con datos en tempo real automatizados de **MeteoGalicia**")

# Verificación inicial de que os ficheiros mestres existen
if not os.path.exists(FICHEIRO_MDT) or not os.path.exists(FICHEIRO_COMBUSTIBLE):
    st.error(f"❌ Non se atopan os mapas mestres de Galicia (`{FICHEIRO_MDT}` ou `{FICHEIRO_COMBUSTIBLE}`) no cartafol do proxecto.")
    st.stop()

with st.sidebar:
    st.header("Configuración Principal")
    api_key = st.text_input("MeteoSIX API KEY", type="password", help="Introduce a túa chave da API de MeteoGalicia")
    horas_sim = st.slider("Horizonte de simulación (horas)", 1, 12, 6)
    
    with st.expander("⚙️ Parámetros Avanzados do Motor"):
        st.caption("Configuración interna do comportamento físico")
        sigma_blur = st.slider("Suavizado de vento (Sigma)", 1, 5, 3)
        c_wind = st.number_input("Factor de influencia do vento", 0.01, 0.10, 0.05)

    if st.button("🔄 Limpar punto de ignición", use_container_width=True):
        st.session_state['foco_ignicion'] = None
        st.rerun()

# --- 4. SELECCIÓN DE IGNICIÓN (MAPA ANCORADO A GALICIA) ---
st.subheader("1. Selecciona o foco de ignición no mapa de Galicia")

min_lat, max_lat = 41.8, 43.9
min_lon, max_lon = -9.4, -6.7
map_center = [42.8, -7.9]
map_zoom = 8

if st.session_state['foco_ignicion']:
    map_center = st.session_state['foco_ignicion']
    map_zoom = 11

m = folium.Map(location=map_center, zoom_start=map_zoom, min_zoom=8,
    min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, max_bounds=True)

if st.session_state['foco_ignicion']:
    folium.Marker(location=st.session_state['foco_ignicion'], popup="Ignición", icon=Icon(color='red', icon='fire', prefix='fa')).add_to(m)

mapa_data = st_folium(m, height=450, width=600, key="mapa_galicia")

if mapa_data["last_clicked"]:
    clicked_coords = (mapa_data["last_clicked"]["lat"], mapa_data["last_clicked"]["lng"])
    if clicked_coords != st.session_state['foco_ignicion']:
        st.session_state['foco_ignicion'] = clicked_coords
        st.rerun()

ignicion_coords = st.session_state['foco_ignicion']

if ignicion_coords:
    st.success(f"📍 Punto seleccionado: Lat {ignicion_coords[0]:.4f}, Lon {ignicion_coords[1]:.4f}")
else:
    st.info("Fai clic no mapa para establecer o inicio do lume.")

# --- 5. EXECUCIÓN AUTOMÁTICA POR VENTÁS ---
if st.button("🚀 Iniciar Simulación Autonómica", type="primary"):
    if not api_key:
        st.error("⚠️ Introduce a túa API KEY no panel esquerdo.")
    elif not ignicion_coords:
        st.error("⚠️ Selecciona un punto no mapa de Galicia.")
    else:
        with st.spinner("Extreendo fiestra xeográfica e procesando física..."):
            try:
                # 1. Abrir o MDT mestre para calcular a ventá de recortes
                with rasterio.open(FICHEIRO_MDT) as src_mdt:
                    crs_raster = src_mdt.crs
                    
                    # Convertir Clic (WGS84) a Coordenadas Proxectadas (UTM 29N)
                    trans_click = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)
                    x_click, y_click = trans_click.transform(ignicion_coords[1], ignicion_coords[0])
                    
                    # Definir o Bounding Box da ventá de simulación ao redor do clic
                    left = x_click - RADIO_SIMULACION_METROS
                    right = x_click + RADIO_SIMULACION_METROS
                    bottom = y_click - RADIO_SIMULACION_METROS
                    top = y_click + RADIO_SIMULACION_METROS
                    
                    # Crear a Fiestra Xeográfica (Window)
                    window = from_bounds(left, bottom, right, top, transform=src_mdt.transform)
                    
                    # Ler EXCLUSIVAMENTE ese cachiño de Galicia
                    elev = src_mdt.read(1, window=window).astype(float)
                    elev[elev == src_mdt.nodata] = np.nan
                    
                    # Actualizar a xeorreferenciación local da ventá
                    window_transform = rasterio.windows.transform(window, src_mdt.transform)
                    cell_size = window_transform[0]
                    rows, cols = elev.shape
                    
                    # Obter os límites locais reais para as consultas de vento
                    window_bounds = rasterio.windows.bounds(window, src_mdt.transform)
                    
                    # Calcular a posición exacta do píxel de ignición dentro do recorte
                    py, px = src_mdt.index(x_click, y_click)
                    py_local = py - int(window.row_off)
                    px_local = px - int(window.col_off)

                # 2. Ler o mesmo cachiño correspondente no mapa de combustibles
                with rasterio.open(FICHEIRO_COMBUSTIBLE) as src_fuel:
                    fuel = src_fuel.read(1, window=window)

                # 3. Consulta Meteorolóxica restrinxida á nosa ventá de 10x10km
                viento_data, error = consultar_viento_api(api_key, window_bounds, crs_raster)
                if error:
                    st.error(error); st.stop()
                
                pos, u_pts, v_pts = viento_data
                target_x = np.linspace(left, right, cols)
                target_y = np.linspace(top, bottom, rows)
                t_x_grid, t_y_grid = np.meshgrid(target_x, target_y)
                
                # Interpolación local do vento
                U_interp = griddata(pos, u_pts, (t_x_grid, t_y_grid), method='cubic')
                V_interp = griddata(pos, v_pts, (t_x_grid, t_y_grid), method='cubic')
                U_interp = np.where(np.isnan(U_interp), np.nanmean(U_interp), U_interp)
                V_interp = np.where(np.isnan(V_interp), np.nanmean(V_interp), V_interp)
                
                U_viento = gaussian_filter(U_interp, sigma=sigma_blur)
                V_viento = gaussian_filter(V_interp, sigma=sigma_blur)

                # 4. Física de Rothermel local
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

                # 5. Motor de Isocronas (MCP Geometric con 8 veciños implicito)
                cost_matrix = np.full_like(ros_max, np.inf, dtype=np.float32)
                burnable = ros_max > 0.01
                cost_matrix[burnable] = cell_size / ros_max[burnable]

                mcp = MCP_Geometric(cost_matrix)
                tiempos, _ = mcp.find_costs(starts=[(py_local, px_local)])
                tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
                tiempos[tiempos > (horas_sim * 60)] = np.nan 

                # 6. Visualización final interactiva con Folium (CON ISOCRONAS)
                st.subheader("2. Resultados da Simulación (Mapa Interactivo con Isocronas)")
                
                max_mins = np.nanmax(tiempos)
                if max_mins > 0:
                    # A. Transformar coordenadas
                    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
                    
                    if hasattr(window_bounds, 'left'):
                        w_left, w_bottom, w_right, w_top = window_bounds.left, window_bounds.bottom, window_bounds.right, window_bounds.top
                    else:
                        w_left, w_bottom, w_right, w_top = window_bounds
                        
                    lon_min, lat_min = transformer_to_wgs84.transform(w_left, w_bottom)
                    lon_max, lat_max = transformer_to_wgs84.transform(w_right, w_top)
                    bounds_latlon = [[lat_min, lon_min], [lat_max, lon_max]]

                    # B. Crear a imaxe RGBA do fondo (Máis transparente para que destaquen as liñas)
                    norm = mcolors.Normalize(vmin=0, vmax=max_mins)
                    cmap = plt.get_cmap('YlOrRd') 
                    rgba_img = cmap(norm(tiempos))
                    rgba_img[np.isnan(tiempos), 3] = 0  # Fondo transparente
                    
                    # C. Montar o mapa
                    m_resultado = folium.Map(
                        location=[ignicion_coords[0], ignicion_coords[1]], 
                        zoom_start=13, 
                        tiles='OpenTopoMap'
                    )
                    
                    # D. Capa base: A mancha continua (Opacidade rebaixada)
                    folium.raster_layers.ImageOverlay(
                        image=rgba_img,
                        bounds=bounds_latlon,
                        opacity=0.4,
                        name="Mancha Térmica",
                    ).add_to(m_resultado)

                    # 🌟 E. A MAXIA DAS ISOCRONAS 🌟
                    step = 60 if max_mins > 120 else 15
                    niveles = np.arange(step, max_mins, step)
                    
                    # Extraer os contornos matemáticos da matriz de tempos
                    for nivel in niveles:
                        # find_contours atopa os píxeles exactos onde o tempo = nivel
                        contours = measure.find_contours(tiempos, nivel)
                        
                        for contour in contours:
                            linea_latlon = []
                            for fila, col in contour:
                                # Transformar píxel (fila, columna) a coordenadas xeográficas reais
                                x_utm, y_utm = window_transform * (col, fila)
                                lon_c, lat_c = transformer_to_wgs84.transform(x_utm, y_utm)
                                linea_latlon.append([lat_c, lon_c])
                            
                            # Debuxar a liña sobre o mapa interactivo
                            folium.PolyLine(
                                locations=linea_latlon,
                                color='red',
                                weight=2.5,
                                opacity=0.9,
                                tooltip=f"Isocrona: {int(nivel)} minutos", # Mensaxe ao pasar o rato!
                                name=f"Avance {int(nivel)} min"
                            ).add_to(m_resultado)

                    # Marcador de inicio
                    folium.Marker(
                        location=ignicion_coords, 
                        popup="Foco de Ignición", 
                        icon=folium.Icon(color='black', icon='fire', prefix='fa')
                    ).add_to(m_resultado)
                    
                    folium.LayerControl().add_to(m_resultado)
                    
                    # Renderizar o mapa final estático pero interactivo
                    components.html(m_resultado._repr_html_(), width=800, height=550)
                    
                    st.success(f"✅ Simulación completada. O lume estendeuse durante {max_mins/60:.2f} horas.")
                else:
                    st.warning("O lume non se propagou (posible zona incombustible).")

            except Exception as e:
                st.error(f"❌ Erro crítico no motor analítico: {e}")