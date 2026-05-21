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

# --- 1. CONFIGURACIÓN DE PÁGINA E ESTILOS MINIMALISTAS ---
st.set_page_config(page_title="Simulador de Incendios - MeteoGalicia v5", layout="wide")

# 🌟 CSS INXECTADO PARA LIMPAR A INTERFACE (Restaurado o header)
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 2rem; padding-right: 2rem; }
    footer {visibility: hidden;} 
    div[data-testid="metric-container"] {
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.1);
        padding: 5% 10% 5% 10%;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

FICHEIRO_MDT = "MDT_Galicia_25m.tif"
FICHEIRO_COMBUSTIBLE = "Combustibles_Galicia_25m.tif" 

if 'foco_ignicion' not in st.session_state:
    st.session_state['foco_ignicion'] = None 

# --- 2. FUNCIONES LÓGICAS (Meteorología) ---
def consultar_viento_api(api_key, bounds, crs_raster):
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
    params = {"coords": coords_str, "variables": "wind", "models": "WRF", "format": "application/json", "API_KEY": api_key}

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

# --- 3. CABECEIRA PRINCIPAL ---
if not os.path.exists(FICHEIRO_MDT) or not os.path.exists(FICHEIRO_COMBUSTIBLE):
    st.error(f"❌ Non se atopan os mapas mestres de Galicia (`{FICHEIRO_MDT}` ou `{FICHEIRO_COMBUSTIBLE}`).")
    st.stop()

st.title("🔥 Simulador Automático de Propagación de Incendios")
st.markdown("Cálculo baseado no modelo físico de **Rothermel** con datos en tempo real automatizados de **MeteoGalicia**")
st.markdown("---")

# --- 4. SELECCIÓN DE IGNICIÓN E CONFIGURACIÓN (Dúas Columnas) ---
col_mapa, col_config = st.columns([1.5, 1])

with col_mapa:
    st.markdown("### 📍 1. Selección do Foco (Galicia)")
    st.markdown("<p style='margin-bottom: 5px; opacity: 0.8;'>Fai clic no mapa para establecer o inicio do lume.</p>", unsafe_allow_html=True)
    
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

with col_config:
    st.markdown("### ⚙️ 2. Parámetros e Climatoloxía")
    
    st.markdown("**Horizonte de predición**")
    horas_sim = st.slider("Horas a simular", 1, 12, 6, help="Aumenta o radio de simulación dinamicamente.")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Meteoroloxía Dinámica**")
    usar_manual = st.checkbox("Activar inxestión manual (Override)", value=True)
    
    if usar_manual:
        st.info("Modo Override Activo.")
        v_velocidad = st.slider("Velocidade do vento (km/h)", 0.0, 50.0, 15.0)
        
        grafico_vento = st.empty()
        v_direccion = st.slider("Dirección do vento (º)", 0, 360, 45, step=5)
        
        puntos_cardinais = ["Norte", "Nordés", "Leste", "Sueste", "Sur", "Suroeste", "Oeste", "Noroeste"]
        nome_vento = puntos_cardinais[int(round(v_direccion / 45)) % 8]
        
        grafico_vento.markdown(
            f"""
            <div style="display: flex; align-items: center; background-color: rgba(128, 128, 128, 0.1); padding: 10px; border-radius: 8px; margin-bottom: -10px;">
                <div style="font-size: 28px; margin-right: 15px; transform: rotate({v_direccion}deg); display: inline-block; transition: transform 0.2s ease-out;">⬇️</div>
                <div style="line-height: 1.2;">
                    <strong>Vento {nome_vento}</strong><br>
                    <span style="font-size: 12px; opacity: 0.8;">A frecha indica o avance</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        v_humedad = st.slider("Humidade Relativa (%)", 10, 100, 30)
        api_key = ""
    else:
        api_key = st.text_input("MeteoSIX API KEY", type="password")
        st.caption("Fallback en caso de erro na rede: Nordés 15km/h, Humidade 30%.")

# Confirmación de coordenadas
if ignicion_coords:
    col_success, _, _ = st.columns([1.5, 1, 1])
    with col_success:
        st.success(f"📍 Punto seleccionado: Lat {ignicion_coords[0]:.4f}, Lon {ignicion_coords[1]:.4f}")

st.markdown("<br>", unsafe_allow_html=True)

# --- 5. EXECUCIÓN E MOTOR FÍSICO ---
col1, col2, _, _ = st.columns(4)
with col1:
    limpar_foco = st.button("🔄 Limpar punto", type="secondary", use_container_width=True)    
with col2:
    iniciar_sim = st.button("🚀 Iniciar Simulación", type="primary", use_container_width=True)

if limpar_foco:
    st.session_state['foco_ignicion'] = None
    st.rerun()

if iniciar_sim:
    if not usar_manual and not api_key:
        st.error("⚠️ Introduce a túa API KEY ou activa o modo manual.")
    elif not ignicion_coords:
        st.error("⚠️ Selecciona un punto no mapa de Galicia.")
    else:
        st.markdown("---")
        with st.spinner("Procesando matriz xeoespacial e propagación física..."):
            try:
                RADIO_SIMULACION_METROS = int(horas_sim * 2500)

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
                    
                    w_trans = rasterio.windows.transform(window, src_mdt.transform)
                    cell_size = w_trans[0]
                    rows, cols = elev.shape
                    w_bounds = rasterio.windows.bounds(window, src_mdt.transform)
                    
                    py, px = src_mdt.index(x_click, y_click)
                    py_local, px_local = py - int(window.row_off), px - int(window.col_off)

                with rasterio.open(FICHEIRO_COMBUSTIBLE) as src_fuel:
                    fuel = src_fuel.read(1, window=window)

                t_x, t_y = np.linspace(left, right, cols), np.linspace(top, bottom, rows)
                tx_grid, ty_grid = np.meshgrid(t_x, t_y)

                # Xerarquía meteorolóxica
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
                        pos = np.array([[left, bottom], [left, top], [right, bottom], [right, top]])
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

                # Amortiguación
                f_h = 1.0 if rh_ambiente < 30 else (0.7 if rh_ambiente < 60 else (0.4 if rh_ambiente <= 80 else 0.1))

                # Rothermel
                dy, dx = np.gradient(elev, cell_size)
                slp, asp = np.arctan(np.sqrt(dx**2 + dy**2)), np.arctan2(-dx, dy)
                Phi_S = 5.275 * (np.tan(slp)**2)
                Sx, Sy = Phi_S * np.sin(asp + np.pi), Phi_S * np.cos(asp + np.pi)
                
                V_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
                R0 = np.zeros_like(fuel, dtype=float)
                for m, v in V_R0.items(): R0[fuel == m] = v
                
                ros_max = R0 * (1 + np.sqrt((Sx + (0.05 * U_v))**2 + (Sy + (0.05 * V_v))**2)) * f_h

                # MCP Geometric
                cost = np.full_like(ros_max, np.inf, dtype=np.float32)
                cost[ros_max > 0.01] = cell_size / ros_max[ros_max > 0.01]
                tiempos, _ = MCP_Geometric(cost).find_costs(starts=[(py_local, px_local)])
                tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
                tiempos[tiempos > (horas_sim * 60)] = np.nan 

                # 6. SAÍDA ANALÍTICA
                max_mins = np.nanmax(tiempos)
                if max_mins > 0:
                    st.markdown("### 📊 3. Informe de Resultados")
                    ha = np.count_nonzero(~np.isnan(tiempos)) * (cell_size**2) / 10000.0
                    
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Superficie Afectada", f"{ha:.1f} ha")
                    k2.metric("Tempo de Avance", f"{max_mins/60:.1f} hr")
                    k3.metric("Vento Medio", f"{v_rep:.1f} km/h")
                    k4.metric("Humidade", f"{rh_ambiente}%")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # 🌟 CORRECCIÓN DO ERRO 'TUPLE' 🌟
                    t_w84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
                    
                    # Comprobamos se w_bounds é un obxecto ou unha tupla
                    if hasattr(w_bounds, 'left'):
                        w_l, w_b, w_r, w_t = w_bounds.left, w_bounds.bottom, w_bounds.right, w_bounds.top
                    else:
                        w_l, w_b, w_r, w_t = w_bounds
                        
                    l_w, b_w = t_w84.transform(w_l, w_b)
                    r_w, t_w = t_w84.transform(w_r, w_t)
                    b_latlon = [[b_w, l_w], [t_w, r_w]]

                    rgba = plt.get_cmap('YlOrRd')(mcolors.Normalize(vmin=0, vmax=max_mins)(tiempos))
                    rgba[np.isnan(tiempos), 3] = 0  
                    
                    m_res = folium.Map(location=[ignicion_coords[0], ignicion_coords[1]], zoom_start=13, tiles='OpenTopoMap')
                    folium.raster_layers.ImageOverlay(image=rgba, bounds=b_latlon, opacity=0.4).add_to(m_res)

                    # Debuxar isocronas
                    for n in np.arange(60 if max_mins > 120 else 15, max_mins, 60 if max_mins > 120 else 15):
                        for c in measure.find_contours(tiempos, n):
                            pts = [[t_w84.transform(*(w_trans * (col, fil)))[1], t_w84.transform(*(w_trans * (col, fil)))[0]] for fil, col in c]
                            folium.PolyLine(locations=pts, color='red', weight=2.5, tooltip=f"{int(n)} min").add_to(m_res)

                    folium.Marker(location=ignicion_coords, icon=Icon(color='black', icon='fire', prefix='fa')).add_to(m_res)
                    folium.LayerControl().add_to(m_res)
                    components.html(m_res._repr_html_(), width=800, height=550)
                else:
                    st.warning("O lume non se propagou (posible zona incombustible ou humidade moi elevada).")
            except Exception as e:
                st.error(f"❌ Erro analítico: {e}")