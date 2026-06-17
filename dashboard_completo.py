import time
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


# Definimos a URL para a descarga directa do modelo do terreo
URL_MDT = "https://www.dropbox.com/scl/fi/ustgvuxtt27aoct9mpfix/MDT_Galicia_25m.tif?rlkey=w4xa3rgzzu8zqydu5ppz6wown&st=ahx8imek&dl=1"
ARQUIVO_MDT = "MDT_Galicia_25m.tif"

# Comprobación de obtención do arquivo do modelo do terreo
def garantir_mapa_mestre():
    if not os.path.exists(ARQUIVO_MDT):
        with st.spinner(f"📥 Descargando topografía de alta resolución ({ARQUIVO_MDT})... Isto levará uns segundos só a primeira vez."):
            try:
                resposta = requests.get(URL_MDT, stream=True)
                resposta.raise_for_status()
                
                # Garda o ficheiro en trozos
                with open(ARQUIVO_MDT, "wb") as f:
                    for chunk in resposta.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                st.success("✅ Topografía descargada correctamente.")
            except Exception as e:
                st.error(f"❌ Erro ao descargar o MDT: {e}")
                st.stop() # Detén a aplicación se non hai mapa


garantir_mapa_mestre()

# --- 1. CONFIGURACIÓN DE PÁGINA E CSS ---
st.set_page_config(page_title="Simulador de Incendios", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* ESCRITORIO */
    .block-container { 
        padding-top: 3rem !important; 
        padding-bottom: 0rem !important; 
        padding-left: 0rem !important; 
        padding-right: 0rem !important; 
        max-width: 100% !important;
    }
    footer {visibility: hidden;} 
    header {background-color: transparent !important;}
    
    div[data-testid="metric-container"] {
        background-color: rgba(255, 255, 255, 0.95);
        border: 1px solid rgba(128, 128, 128, 0.3);
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .barra-ferramentas {
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        margin-bottom: 0.5rem;
    }
    
    .barra-ferramentas h3 {
        margin-top: -14px !important; 
        margin-bottom: 0px !important;  
        padding-top: 0px !important;
    }

    .titulo-app {
        font-size: 24px; 
        font-weight: bold; 
        position: relative; 
        top: -10px; 
        white-space: nowrap;
    }
    .subtitulo-slider {
        text-align: center; 
        font-size: 13px; 
        font-weight: 600; 
        opacity: 0.75; 
        position: relative; 
        top: -15px; 
        pointer-events: none;
        white-space: nowrap;
    }

    /* PANTALLAS MEDIANAS */
    @media screen and (min-width: 769px) and (max-width: 1800px) {
        .titulo-app {
            font-size: 18px !important; 
            white-space: normal !important; 
            line-height: 1.2 !important;
            top: -5px !important;
        }
        .subtitulo-slider {
            font-size: 11px !important;
            white-space: normal !important;
        }
        div[data-testid="stButton"] button p, 
        div[data-testid="stPopover"] button p {
            font-size: 14px !important;
        }
    }

    /* MÓBILES */
    @media screen and (max-width: 768px) {
       
        iframe { height: 450px !important; }
        
        div[data-testid="stMainBlockContainer"], 
        div[data-testid="stAppViewBlockContainer"],
        .main .block-container {
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
        }
        
        div[data-testid="stVerticalBlock"] > div {
            margin-bottom: 0.3rem;
        }

        div[data-testid="stPopoverBody"] {
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
        }
        
        .barra-ferramentas {
            padding-left: 0rem !important;
            padding-right: 0rem !important;
        }
        
        .titulo-app {
            font-size: 22px !important;
            white-space: normal !important; 
            text-align: center !important;
            top: 0px !important;
            margin-bottom: 10px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

FICHEIRO_MDT = "MDT_Galicia_25m.tif"
FICHEIRO_COMBUSTIBLE = "Combustibles_Galicia_25m.tif" 

# Estados de sesión
if 'foco_ignicion' not in st.session_state: st.session_state['foco_ignicion'] = None 
if 'mapa_resultado' not in st.session_state: st.session_state['mapa_resultado'] = None
if 'kpis_resultado' not in st.session_state: st.session_state['kpis_resultado'] = None
if 'ultimo_click_invalido' not in st.session_state: st.session_state['ultimo_click_invalido'] = None
if 'erro_incombustible' not in st.session_state: st.session_state['erro_incombustible'] = False 

# --- 2. FUNCIÓNS LÓXICAS ---
def consultar_viento_api(api_key, bounds, crs_raster):
    transformer_to_wgs84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    if hasattr(bounds, 'left'):
        left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
    else:
        left, bottom, right, top = bounds 

    lon_min, lat_min = transformer_to_wgs84.transform(left, bottom)
    lon_max, lat_max = transformer_to_wgs84.transform(right, top)

    lons = np.linspace(lon_min, lon_max, 4)
    lats = np.linspace(lat_min, lat_max, 4)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    coords_str = ";".join([f"{lon:.4f},{lat:.4f}" for lon, lat in zip(grid_lon.flatten(), grid_lat.flatten())])

    url = "https://servizos.meteogalicia.gal/apiv5/getNumericForecastInfo"
    params = {"coords": coords_str, "variables": "wind", "models": "WRF", "format": "application/json", "API_KEY": api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
    except Exception as e: return None, f"Erro: {e}"

    if "exception" in data: return None, f"Erro API: {data['exception']['message']}"
    
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
        except: continue
    
    return (np.array(puntos_pos), puntos_u, puntos_v), None

if not os.path.exists(FICHEIRO_MDT) or not os.path.exists(FICHEIRO_COMBUSTIBLE):
    st.error(f"❌ Faltan os mapas mestres de Galicia.")
    st.stop()

# --- 3. BARRA SUPERIOR DE FERRAMENTAS ---
st.markdown("<div class='barra-ferramentas'>", unsafe_allow_html=True)

col_titulo, col_slider, col_menu, col_limpar, col_lanzar = st.columns([1.5, 1.5, 1.5, 1, 1.5], vertical_alignment="center")

with col_titulo:
    st.markdown("<div class='titulo-app'>🔥 Simulador de Incendios en Galicia</div>", unsafe_allow_html=True)

with col_slider:
    horas_sim = st.slider("Horas", 1, 12, 6, label_visibility="collapsed")
    st.markdown("<div class='subtitulo-slider'>Horas de predicción</div>", unsafe_allow_html=True)

with col_menu:
    with st.popover("⚙️ Clima e API", use_container_width=True):
        usar_manual = st.checkbox("Control Manual (Override)", value=True)
        if usar_manual:
            v_velocidad = st.slider("Velocidade (km/h)", 0.0, 50.0, 15.0)
            
            grafico_vento = st.empty()
            v_direccion = st.slider("Dirección (º)", 0, 360, 45, step=5)
            
            pts_card = ["Norte", "Nordés", "Leste", "Sueste", "Sur", "Suroeste", "Oeste", "Noroeste"]
            nome_vento = pts_card[int(round(v_direccion / 45)) % 8]
            
            grafico_vento.markdown(
                f"""
                <div style="display: flex; align-items: center; background-color: rgba(128, 128, 128, 0.1); padding: 10px; border-radius: 8px; margin-bottom: 5px; margin-top: 5px;">
                    <div style="font-size: 28px; margin-right: 15px; transform: rotate({v_direccion}deg); display: inline-block; transition: transform 0.2s ease-out;">⬇️</div>
                    <div style="line-height: 1.2;">
                        <strong>Vento {nome_vento}</strong><br>
                        <span style="font-size: 12px; opacity: 0.8;">A frecha indica o avance</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            v_humedad = st.slider("Humidade (%)", 10, 100, 30)
            api_key = ""
        else:
            api_key = st.text_input("MeteoSIX API KEY", type="password")

with col_limpar:
    limpar = st.button("🔄 Reiniciar", use_container_width=True)
with col_lanzar:
    lanzar = st.button("🚀 Simular", type="primary", use_container_width=True)

# Botón de limpeza
if limpar:
    st.session_state['foco_ignicion'] = None
    st.session_state['mapa_resultado'] = None
    st.session_state['kpis_resultado'] = None
    st.session_state['ultimo_click_invalido'] = None 
    st.session_state['erro_incombustible'] = False
    st.rerun()

# RESULTADOS 
if st.session_state['kpis_resultado'] is not None:
    ha, max_mins, vel_reporte, rh_ambiente = st.session_state['kpis_resultado']
    c1, c2, c3, c4 = st.columns(4) 
    c1.metric("Superficie Afectada", f"{ha:.1f} ha")
    c2.metric("Tempo de Avance", f"{max_mins/60:.1f} hr")
    c3.metric("Vento Medio", f"{vel_reporte:.1f} km/h")
    c4.metric("Humidade Ambiente", f"{rh_ambiente}%")
elif st.session_state['erro_incombustible']:
    st.warning("⚠️ O lume non se propagou (posible zona incombustible ou barreira de humidade). Por favor, fai clic noutro punto do mapa.")
elif st.session_state['foco_ignicion']:
    st.success(f"📍 Coordenadas seleccionadas como punto de ignición: {st.session_state['foco_ignicion'][0]:.4f}, {st.session_state['foco_ignicion'][1]:.4f}")

st.markdown("</div>", unsafe_allow_html=True) 

# --- 4. EXECUCIÓN DO MOTOR ---
if lanzar:
    if not usar_manual and not api_key:
        st.error("⚠️ Precísase a API KEY ou o modo manual.")
    elif not st.session_state['foco_ignicion']:
        st.error("⚠️ Marca un punto no mapa xeográfico.")
    else:
        with st.spinner("Procesando malla xeoespacial..."):
            try:
                start_time = time.time()
                
                RADIO_SIMULACION_METROS = int(horas_sim * 2500)
                ignicion_coords = st.session_state['foco_ignicion']

                with rasterio.open(FICHEIRO_MDT) as src_mdt:
                    crs_raster = src_mdt.crs
                    trans_click = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)
                    x_click, y_click = trans_click.transform(ignicion_coords[1], ignicion_coords[0])
                    
                    l, r = x_click - RADIO_SIMULACION_METROS, x_click + RADIO_SIMULACION_METROS
                    b, t = y_click - RADIO_SIMULACION_METROS, y_click + RADIO_SIMULACION_METROS
                    
                    window = from_bounds(l, b, r, t, transform=src_mdt.transform)
                    elev = src_mdt.read(1, window=window).astype(float)
                    elev[elev == src_mdt.nodata] = np.nan
                    
                    w_trans = rasterio.windows.transform(window, src_mdt.transform)
                    cell_size = w_trans[0]
                    rows, cols = elev.shape
                    w_bounds = rasterio.windows.bounds(window, src_mdt.transform)
                    
                    py, px = src_mdt.index(x_click, y_click)
                    py_local, px_local = py - int(window.row_off), px - int(window.col_off)

                with rasterio.open(FICHEIRO_COMBUSTIBLE) as src_fuel:
                    fuel = src_fuel.read(1, window=window)

                t_x, t_y = np.linspace(l, r, cols), np.linspace(t, b, rows)
                tx_grid, ty_grid = np.meshgrid(t_x, t_y)

                if usar_manual:
                    rad = np.radians((v_direccion + 180) % 360)
                    U_v = np.full_like(elev, v_velocidad * np.sin(rad))
                    V_v = np.full_like(elev, v_velocidad * np.cos(rad))
                    rh_ambiente, v_rep = v_humedad, v_velocidad
                else:
                    v_data, err = consultar_viento_api(api_key, w_bounds, crs_raster)
                    if err:
                        st.toast("⚠️ Fallback 30-30-30 activo.")
                        rad = np.radians((45.0 + 180) % 360)
                        pos = np.array([[l, b], [l, t], [r, b], [r, t]])
                        u_pts, v_pts = [15.0 * np.sin(rad)] * 4, [15.0 * np.cos(rad)] * 4
                        rh_ambiente, v_rep = 30.0, 15.0
                    else:
                        pos, u_pts, v_pts = v_data
                        rh_ambiente = 65.0 
                        v_rep = np.mean(np.sqrt(np.array(u_pts)**2 + np.array(v_pts)**2))

                    U_i = griddata(pos, u_pts, (tx_grid, ty_grid), method='cubic')
                    V_i = griddata(pos, v_pts, (tx_grid, ty_grid), method='cubic')
                    U_v = gaussian_filter(np.where(np.isnan(U_i), np.nanmean(u_pts), U_i), sigma=3)
                    V_v = gaussian_filter(np.where(np.isnan(V_i), np.nanmean(v_pts), V_i), sigma=3)

                f_h = 1.0 if rh_ambiente < 30 else (0.7 if rh_ambiente < 60 else (0.4 if rh_ambiente <= 80 else 0.1))

                dy, dx = np.gradient(elev, cell_size)
                slp, asp = np.arctan(np.sqrt(dx**2 + dy**2)), np.arctan2(-dx, dy)
                Phi_S = 5.275 * (np.tan(slp)**2)
                Sx, Sy = Phi_S * np.sin(asp + np.pi), Phi_S * np.cos(asp + np.pi)
                
                V_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
                R0 = np.zeros_like(fuel, dtype=float)
                for m, v in V_R0.items(): R0[fuel == m] = v
                
                # Facer que o vento afecte negativa ou positivamente a velocidade de propagación
                dx_grid, dy_grid = tx_grid - x_click, ty_grid - y_click
                dist_grid = np.sqrt(dx_grid**2 + dy_grid**2) + 1e-6
                
                wind_mag = np.sqrt(U_v**2 + V_v**2) + 1e-6
                u_wind_norm, v_wind_norm = U_v / wind_mag, V_v / wind_mag
                u_dir_norm, v_dir_norm = dx_grid / dist_grid, dy_grid / dist_grid
                
                cos_theta = (u_dir_norm * u_wind_norm) + (v_dir_norm * v_wind_norm)
                
                wind_weight = np.clip(wind_mag / 20.0, 0.0, 0.85) 
                factor_direccion = 1.0 - (wind_weight * (1.0 - cos_theta) / 2.0)
                
                ros_max = R0 * (1 + np.sqrt((Sx + (0.05 * U_v))**2 + (Sy + (0.05 * V_v))**2)) * f_h
                ros_max = ros_max * factor_direccion

                cost = np.full_like(ros_max, np.inf, dtype=np.float32)
                cost[ros_max > 0.01] = cell_size / ros_max[ros_max > 0.01]

                mcp = MCP_Geometric(cost)
                tiempos, _ = mcp.find_costs(starts=[(py_local, px_local)])
                tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
                tiempos[tiempos > (horas_sim * 60)] = np.nan 

                max_mins = np.nanmax(tiempos)
                if max_mins > 0:
                    ha = np.count_nonzero(~np.isnan(tiempos)) * (cell_size**2) / 10000.0
                    
                    t_w84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
                    if hasattr(w_bounds, 'left'): w_l, w_b, w_r, w_t = w_bounds.left, w_bounds.bottom, w_bounds.right, w_bounds.top
                    else: w_l, w_b, w_r, w_t = w_bounds
                        
                    l_w, b_w = t_w84.transform(w_l, w_b)
                    r_w, t_w = t_w84.transform(w_r, w_t)
                    b_latlon = [[b_w, l_w], [t_w, r_w]]

                    rgba = plt.get_cmap('YlOrRd')(mcolors.Normalize(vmin=0, vmax=max_mins)(tiempos))
                    rgba[np.isnan(tiempos), 3] = 0  
                    
                    m_res = folium.Map(location=[ignicion_coords[0], ignicion_coords[1]], zoom_start=13, tiles='OpenTopoMap')
                    folium.raster_layers.ImageOverlay(image=rgba, bounds=b_latlon, opacity=0.4).add_to(m_res)

                    for n in np.arange(60 if max_mins > 120 else 15, max_mins, 60 if max_mins > 120 else 15):
                        for c in measure.find_contours(tiempos, n):
                            pts = [[t_w84.transform(*(w_trans * (col, fil)))[1], t_w84.transform(*(w_trans * (col, fil)))[0]] for fil, col in c]
                            folium.PolyLine(locations=pts, color='red', weight=2.5, tooltip=f"{int(n)} min").add_to(m_res)

                    folium.Marker(location=ignicion_coords, icon=Icon(color='black', icon='fire', prefix='fa')).add_to(m_res)
                    
                    # Resultados de tempo
                    tempo_exec = time.time() - start_time
                    print(f"\n==================================================")
                    print(f"🔥 SIMULACIÓN REMATADA ({horas_sim} HORAS) 🔥")
                    print(f"⏱️ Tempo de execución: {tempo_exec:.4f} segundos")
                    print(f"==================================================\n")
                    
                    st.session_state['mapa_resultado'] = m_res._repr_html_()
                    st.session_state['kpis_resultado'] = (ha, max_mins, v_rep, rh_ambiente) # Restaurado a 4 valores
                    st.session_state['erro_incombustible'] = False 
                    st.rerun() 
                else:
                    st.session_state['foco_ignicion'] = None
                    st.session_state['mapa_resultado'] = None
                    st.session_state['kpis_resultado'] = None
                    st.session_state['erro_incombustible'] = True
                    st.rerun()

            except Exception as e:
                st.error(f"❌ Erro analítico: {e}")

# --- 5. RENDERIZADO DO MAPA ---
if st.session_state['mapa_resultado'] is not None:
    components.html(st.session_state['mapa_resultado'], height=800)
else:
    min_lat, max_lat = 41.8, 43.9
    min_lon, max_lon = -9.4, -6.7
    map_center = [42.8, -7.9]
    map_zoom = 9

    if st.session_state['foco_ignicion']:
        map_center = st.session_state['foco_ignicion']
        map_zoom = 11

    m = folium.Map(location=map_center, zoom_start=map_zoom, min_zoom=9,
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, max_bounds=True, tiles='OpenTopoMap')

    if st.session_state['foco_ignicion']:
        folium.Marker(location=st.session_state['foco_ignicion'], popup="Ignición", icon=Icon(color='red', icon='fire', prefix='fa')).add_to(m)

    mapa_data = st_folium(m, height=800, use_container_width=True, key="mapa_galicia")

    if mapa_data["last_clicked"]:
        lat_c = mapa_data["last_clicked"]["lat"]
        lon_c = mapa_data["last_clicked"]["lng"]
        clicked_coords = (lat_c, lon_c)
        
        if clicked_coords != st.session_state['foco_ignicion'] and clicked_coords != st.session_state['ultimo_click_invalido']:
            punto_valido = False
            
            try:
                with rasterio.open(FICHEIRO_MDT) as src:
                    t = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    x, y = t.transform(lon_c, lat_c)
                    py, px = src.index(x, y)
                    
                    if 0 <= py < src.height and 0 <= px < src.width:
                        pixel = src.read(1, window=rasterio.windows.Window(col_off=px, row_off=py, width=1, height=1))
                        if pixel[0][0] != src.nodata:
                            punto_valido = True
            except Exception:
                pass 
            
            if punto_valido:
                st.session_state['foco_ignicion'] = clicked_coords
                st.session_state['ultimo_click_invalido'] = None
                st.session_state['erro_incombustible'] = False 
                st.rerun()
            else:
                st.session_state['ultimo_click_invalido'] = clicked_coords
                st.toast("❌ Localización inválida: Por favor, selecciona un foco de lume válido dentro de Galicia.", icon="🚫")