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

# --- 1. CONFIGURACIÓN DE PÁGINA E RUTAS ---
st.set_page_config(page_title="Simulador de Incendios - MeteoGalicia v5", layout="wide")

FICHEIRO_MDT = "MDT_Galicia_25m.tif"
FICHEIRO_COMBUSTIBLE = "Combustibles_Galicia_25m.tif" 

if 'foco_ignicion' not in st.session_state:
    st.session_state['foco_ignicion'] = None 

# --- 2. FUNCIONES LÓGICAS (Meteorología) ---
def consultar_viento_api(api_key, bounds, crs_raster):
    """Obtén e procesa o vento desde a API v5 aplicando transformacións topolóxicas"""
    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    
    if hasattr(bounds, 'left'):
        left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
    else:
        left, bottom, right, top = bounds 

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

if not os.path.exists(FICHEIRO_MDT) or not os.path.exists(FICHEIRO_COMBUSTIBLE):
    st.error(f"❌ Non se atopan os mapas mestres de Galicia (`{FICHEIRO_MDT}` ou `{FICHEIRO_COMBUSTIBLE}`) no cartafol do proxecto.")
    st.stop()

with st.sidebar:
    st.header("Configuración Principal")
    horas_sim = st.slider("Horizonte de simulación (horas)", 1, 12, 6)
    
    # 🌟 NIVEL 1: Controis Manuais de Climatoloxía (Override)
    st.subheader("Climatoloxía Dinámica")
    usar_manual = st.checkbox("Activar inxestión manual (Override)", value=True, 
                              help="Anula a API e permite probar escenarios meteorolóxicos extremos.")
    
    if usar_manual:
        st.info("Modo Override Activo. Ignorando rede externa.")
        v_velocidad = st.slider("Velocidade do vento (km/h)", 0.0, 50.0, 15.0)
        
        # 1. 🌟 RESERVAMOS O ESPAZO: Creamos un contedor baleiro XUSTO ENRIBA do slider
        grafico_vento = st.empty()
        
        # 2. Poñemos o control deslizante xusto debaixo
        v_direccion = st.slider("Dirección do vento (º desde o Norte)", 0, 360, 45, step=5)
        
        # 3. Calculamos o texto baseándonos no que elixiu o usuario
        puntos_cardinais = ["Norte (N)", "Nordés (NE)", "Leste (E)", "Sueste (SE)", 
                            "Sur (S)", "Suroeste (SO)", "Oeste (O)", "Noroeste (NO)"]
        indice_cardinal = int(round(v_direccion / 45)) % 8
        nome_vento = puntos_cardinais[indice_cardinal]
        
        # 4. 🌟 INXECTAMOS O GRÁFICO: Enchemos o contedor que deixamos arriba coa frecha e o HTML
        grafico_vento.markdown(
            f"""
            <div style="display: flex; align-items: center; background-color: rgba(128, 128, 128, 0.1); padding: 10px; border-radius: 8px; margin-bottom: -10px;">
                <div style="font-size: 32px; margin-right: 15px; transform: rotate({v_direccion}deg); display: inline-block; transition: transform 0.2s ease-out;">
                    ⬇️
                </div>
                <div style="line-height: 1.3;">
                    <strong>Vento de compoñente {nome_vento}</strong><br>
                    <span style="font-size: 13px; opacity: 0.8;">A frecha indica cara a onde empuxa o lume</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        # ----------------------------------
        
        v_humedad = st.slider("Humidade Relativa (%)", 10, 100, 30)
        api_key = ""
    else:
        api_key = st.text_input("MeteoSIX API KEY", type="password", help="Introduce a túa chave API")
        st.caption("Se a conexión falla, aplicarase o escenario crítico por defecto (Nordés 15km/h, Humidade 30%).")
    
    with st.expander("⚙️ Parámetros Avanzados do Motor"):
        sigma_blur = st.slider("Suavizado de vento (Sigma)", 1, 5, 3)
        c_wind = st.number_input("Factor de influencia do vento", 0.01, 0.10, 0.05)

    if st.button("🔄 Limpar punto de ignición", use_container_width=True):
        st.session_state['foco_ignicion'] = None
        st.rerun()

# --- 4. SELECCIÓN DE IGNICIÓN (MAPA) ---
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

# --- 5. EXECUCIÓN E MOTOR FÍSICO ---
if st.button("🚀 Iniciar Simulación Autonómica", type="primary"):
    if not usar_manual and not api_key:
        st.error("⚠️ Introduce a túa API KEY no panel esquerdo ou activa o modo manual.")
    elif not ignicion_coords:
        st.error("⚠️ Selecciona un punto no mapa de Galicia.")
    else:
        with st.spinner("Deseñando ventá espacial e procesando motor físico..."):
            try:
                # 🌟 AXUSTE DE VENTÁ DINÁMICA: Crece coas horas de simulación (Evita o estrangulamento perimetral)
                RADIO_SIMULACION_METROS = int(horas_sim * 2500)

                # 1. Abrir MDT
                with rasterio.open(FICHEIRO_MDT) as src_mdt:
                    crs_raster = src_mdt.crs
                    trans_click = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)
                    x_click, y_click = trans_click.transform(ignicion_coords[1], ignicion_coords[0])
                    
                    left = x_click - RADIO_SIMULACION_METROS
                    right = x_click + RADIO_SIMULACION_METROS
                    bottom = y_click - RADIO_SIMULACION_METROS
                    top = y_click + RADIO_SIMULACION_METROS
                    
                    window = from_bounds(left, bottom, right, top, transform=src_mdt.transform)
                    elev = src_mdt.read(1, window=window).astype(float)
                    elev[elev == src_mdt.nodata] = np.nan
                    
                    window_transform = rasterio.windows.transform(window, src_mdt.transform)
                    cell_size = window_transform[0]
                    rows, cols = elev.shape
                    window_bounds = rasterio.windows.bounds(window, src_mdt.transform)
                    
                    py, px = src_mdt.index(x_click, y_click)
                    py_local = py - int(window.row_off)
                    px_local = px - int(window.col_off)

                # 2. Ler Combustibles
                with rasterio.open(FICHEIRO_COMBUSTIBLE) as src_fuel:
                    fuel = src_fuel.read(1, window=window)

                # 3. 🌟 XERARQUÍA DE INXESTIÓN CLIMATOLÓXICA (Niveis 1, 2 e 3)
                target_x = np.linspace(left, right, cols)
                target_y = np.linspace(top, bottom, rows)
                t_x_grid, t_y_grid = np.meshgrid(target_x, target_y)

                if usar_manual:
                    # --- NIVEL 1: Override Manual ---
                    rad = np.radians((v_direccion + 180) % 360)
                    U_viento = np.full_like(elev, v_velocidad * np.sin(rad))
                    V_viento = np.full_like(elev, v_velocidad * np.cos(rad))
                    rh_ambiente = v_humedad
                else:
                    # --- NIVEL 2: API MeteoGalicia ---
                    viento_data, error = consultar_viento_api(api_key, window_bounds, crs_raster)
                    
                    if error:
                        # --- NIVEL 3: Fallback de Emerxencia ---
                        st.warning(f"⚠️ Erro de rede ({error}). Activando Fallback 30-30-30 (Nordés, RH 30%).")
                        velocidad_fallback = 15.0
                        direccion_fallback = 45.0
                        rad = np.radians((direccion_fallback + 180) % 360)
                        
                        pos = np.array([[left, bottom], [left, top], [right, bottom], [right, top]])
                        u_pts = [velocidad_fallback * np.sin(rad)] * 4
                        v_pts = [velocidad_fallback * np.cos(rad)] * 4
                        rh_ambiente = 30.0
                    else:
                        pos, u_pts, v_pts = viento_data
                        rh_ambiente = 65.0 # Valor estándar se non se captura a humidade da API

                    # Interpolación espacial só se usamos datos en puntos (Nivel 2 ou 3)
                    U_interp = griddata(pos, u_pts, (t_x_grid, t_y_grid), method='cubic')
                    V_interp = griddata(pos, v_pts, (t_x_grid, t_y_grid), method='cubic')
                    U_interp = np.where(np.isnan(U_interp), np.nanmean(U_interp), U_interp)
                    V_interp = np.where(np.isnan(V_interp), np.nanmean(V_interp), V_interp)
                    
                    U_viento = gaussian_filter(U_interp, sigma=sigma_blur)
                    V_viento = gaussian_filter(V_interp, sigma=sigma_blur)

                # Aplicación da discretización de Humidade (Amortiguación)
                if rh_ambiente < 30: factor_humedad = 1.0
                elif 30 <= rh_ambiente < 60: factor_humedad = 0.7
                elif 60 <= rh_ambiente <= 80: factor_humedad = 0.4
                else: factor_humedad = 0.1

                # 4. Física de Rothermel local
                dy, dx = np.gradient(elev, cell_size)
                slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
                aspect_rad = np.arctan2(-dx, dy)
                
                Phi_S = 5.275 * (np.tan(slope_rad)**2)
                Sx, Sy = Phi_S * np.sin(aspect_rad + np.pi), Phi_S * np.cos(aspect_rad + np.pi)
                
                VALORES_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
                R0 = np.zeros_like(fuel, dtype=float)
                for m, v in VALORES_R0.items(): R0[fuel == m] = v
                
                Push_X, Push_Y = Sx + (c_wind * U_viento), Sy + (c_wind * V_viento)
                
                # 🌟 Incorporación do factor_humedad ao cálculo final de velocidade
                ros_max = R0 * (1 + np.sqrt(Push_X**2 + Push_Y**2)) * factor_humedad

                # 5. Motor de Isocronas (MCP Geometric)
                cost_matrix = np.full_like(ros_max, np.inf, dtype=np.float32)
                burnable = ros_max > 0.01
                cost_matrix[burnable] = cell_size / ros_max[burnable]

                mcp = MCP_Geometric(cost_matrix)
                tiempos, _ = mcp.find_costs(starts=[(py_local, px_local)])
                tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
                tiempos[tiempos > (horas_sim * 60)] = np.nan 

                # 6. Visualización final interactiva
                st.subheader("2. Resultados da Simulación (Mapa Interactivo con Isocronas)")
                
                max_mins = np.nanmax(tiempos)
                if max_mins > 0:
                    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
                    
                    if hasattr(window_bounds, 'left'):
                        w_left, w_bottom, w_right, w_top = window_bounds.left, window_bounds.bottom, window_bounds.right, window_bounds.top
                    else:
                        w_left, w_bottom, w_right, w_top = window_bounds
                        
                    lon_min, lat_min = transformer_to_wgs84.transform(w_left, w_bottom)
                    lon_max, lat_max = transformer_to_wgs84.transform(w_right, w_top)
                    bounds_latlon = [[lat_min, lon_min], [lat_max, lon_max]]

                    norm = mcolors.Normalize(vmin=0, vmax=max_mins)
                    cmap = plt.get_cmap('YlOrRd') 
                    rgba_img = cmap(norm(tiempos))
                    rgba_img[np.isnan(tiempos), 3] = 0  
                    
                    m_resultado = folium.Map(
                        location=[ignicion_coords[0], ignicion_coords[1]], 
                        zoom_start=13, 
                        tiles='OpenTopoMap'
                    )
                    
                    folium.raster_layers.ImageOverlay(
                        image=rgba_img,
                        bounds=bounds_latlon,
                        opacity=0.4,
                        name="Mancha Térmica",
                    ).add_to(m_resultado)

                    step = 60 if max_mins > 120 else 15
                    niveles = np.arange(step, max_mins, step)
                    
                    for nivel in niveles:
                        contours = measure.find_contours(tiempos, nivel)
                        for contour in contours:
                            linea_latlon = []
                            for fila, col in contour:
                                x_utm, y_utm = window_transform * (col, fila)
                                lon_c, lat_c = transformer_to_wgs84.transform(x_utm, y_utm)
                                linea_latlon.append([lat_c, lon_c])
                            
                            folium.PolyLine(
                                locations=linea_latlon,
                                color='red',
                                weight=2.5,
                                opacity=0.9,
                                tooltip=f"Isocrona: {int(nivel)} minutos", 
                                name=f"Avance {int(nivel)} min"
                            ).add_to(m_resultado)

                    folium.Marker(
                        location=ignicion_coords, 
                        popup="Foco de Ignición", 
                        icon=folium.Icon(color='black', icon='fire', prefix='fa')
                    ).add_to(m_resultado)
                    
                    folium.LayerControl().add_to(m_resultado)
                    components.html(m_resultado._repr_html_(), width=800, height=550)
                    
                    st.success(f"✅ Simulación completada. O lume estendeuse durante {max_mins/60:.2f} horas (Humidade ambiente modelada: {rh_ambiente}%).")
                else:
                    st.warning("O lume non se propagou (posible zona incombustible ou humidade extrema).")

            except Exception as e:
                st.error(f"❌ Erro crítico no motor analítico: {e}")