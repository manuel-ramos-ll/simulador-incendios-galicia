# app.py
import os
import requests
import streamlit as st
import rasterio
import folium
from folium import Icon
from pyproj import Transformer
from streamlit_folium import st_folium

# Importamos o noso motor (Script 05 encapsulado)
from script_05_motor import simular_incendio

# --- 1. CONFIGURACIÓN DE DESCARGAS E CONSTANTES ---
URL_MDT = "https://www.dropbox.com/scl/fi/ustgvuxtt27aoct9mpfix/MDT_Galicia_25m.tif?rlkey=w4xa3rgzzu8zqydu5ppz6wown&st=ahx8imek&dl=1"
FICHEIRO_MDT = "MDT_Galicia_25m.tif"
FICHEIRO_COMBUSTIBLE = "Combustibles_Galicia_25m.tif" 

def garantir_mapa_mestre():
    if not os.path.exists(FICHEIRO_MDT):
        with st.spinner(f"📥 Descargando topografía de alta resolución... Isto levará uns segundos só a primeira vez."):
            try:
                resposta = requests.get(URL_MDT, stream=True)
                resposta.raise_for_status()
                with open(FICHEIRO_MDT, "wb") as f:
                    for chunk in resposta.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                st.success("✅ Topografía descargada correctamente.")
            except Exception as e:
                st.error(f"❌ Erro ao descargar o MDT: {e}")
                st.stop()

garantir_mapa_mestre()

if not os.path.exists(FICHEIRO_MDT) or not os.path.exists(FICHEIRO_COMBUSTIBLE):
    st.error("❌ Faltan os mapas mestres de Galicia.")
    st.stop()

# --- 2. CONFIGURACIÓN DE PÁGINA E CSS ---
st.set_page_config(page_title="Simulador de Incendios", layout="wide", initial_sidebar_state="collapsed")

def cargar_css(nome_ficheiro):
    with open(nome_ficheiro) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

cargar_css("style.css")

# Estados de sesión
if 'foco_ignicion' not in st.session_state: st.session_state['foco_ignicion'] = None 
if 'mapa_resultado' not in st.session_state: st.session_state['mapa_resultado'] = None
if 'kpis_resultado' not in st.session_state: st.session_state['kpis_resultado'] = None
if 'ultimo_click_invalido' not in st.session_state: st.session_state['ultimo_click_invalido'] = None
if 'erro_incombustible' not in st.session_state: st.session_state['erro_incombustible'] = False 

# --- 3. BARRA SUPERIOR DE FERRAMENTAS ---
st.markdown("<div class='barra-ferramentas'>", unsafe_allow_html=True)
col_titulo, col_slider, col_menu, col_limpar, col_lanzar = st.columns([1.5, 1.5, 1.5, 1, 1.5], vertical_alignment="center")

with col_titulo: st.markdown("<div class='titulo-app'>🔥 Simulador de Incendios en Galicia</div>", unsafe_allow_html=True)
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
                f"""<div style="display: flex; align-items: center; background-color: rgba(128, 128, 128, 0.1); padding: 10px; border-radius: 8px; margin-bottom: 5px; margin-top: 5px;">
                    <div style="font-size: 28px; margin-right: 15px; transform: rotate({v_direccion}deg); display: inline-block; transition: transform 0.2s ease-out;">⬇️</div>
                    <div style="line-height: 1.2;"><strong>Vento {nome_vento}</strong><br><span style="font-size: 12px; opacity: 0.8;">A frecha indica o avance</span></div></div>""", unsafe_allow_html=True)
            v_humedad = st.slider("Humidade (%)", 10, 100, 30)
            api_key = ""
        else:
            v_velocidad, v_direccion, v_humedad = 0, 0, 0
            api_key = st.text_input("MeteoSIX API KEY", type="password")

with col_limpar: limpar = st.button("🔄 Reiniciar", use_container_width=True)
with col_lanzar: lanzar = st.button("🚀 Simular", type="primary", use_container_width=True)

if limpar:
    for key in ['foco_ignicion', 'mapa_resultado', 'kpis_resultado', 'ultimo_click_invalido']: st.session_state[key] = None
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

# --- 4. EXECUCIÓN E RENDERIZADO ---
if lanzar:
    if not usar_manual and not api_key: st.error("⚠️ Precísase a API KEY ou o modo manual.")
    elif not st.session_state['foco_ignicion']: st.error("⚠️ Marca un punto no mapa xeográfico.")
    else:
        with st.spinner("Procesando malla xeoespacial..."):
            try:
                # CHAMADA AO MOTOR
                m_res, kpis, erro_incombustible, fallback = simular_incendio(
                    st.session_state['foco_ignicion'], horas_sim, usar_manual, 
                    v_velocidad, v_direccion, v_humedad, api_key, 
                    FICHEIRO_MDT, FICHEIRO_COMBUSTIBLE
                )
                
                if fallback: st.toast("⚠️ Fallback 30-30-30 activo.")

                if erro_incombustible:
                    st.session_state['foco_ignicion'] = None
                    st.session_state['mapa_resultado'] = None
                    st.session_state['kpis_resultado'] = None
                    st.session_state['erro_incombustible'] = True
                else:
                    st.session_state['mapa_resultado'] = m_res
                    st.session_state['kpis_resultado'] = kpis 
                    st.session_state['erro_incombustible'] = False 
                
                st.rerun() 
            except Exception as e:
                st.error(f"❌ Erro analítico: {e}")

# MAPA
if st.session_state['mapa_resultado'] is not None:
    st_folium(st.session_state['mapa_resultado'], height=800, use_container_width=True, returned_objects=[], key="mapa_resultado_render")
else:
    min_lat, max_lat, min_lon, max_lon = 41.8, 43.9, -9.4, -6.7
    map_center = st.session_state['foco_ignicion'] if st.session_state['foco_ignicion'] else [42.8, -7.9]
    map_zoom = 11 if st.session_state['foco_ignicion'] else 9

    m = folium.Map(location=map_center, zoom_start=map_zoom, min_zoom=6,
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, max_bounds=False, tiles='OpenTopoMap')

    if st.session_state['foco_ignicion']:
        folium.Marker(location=st.session_state['foco_ignicion'], popup="Ignición", icon=Icon(color='red', icon='fire', prefix='fa')).add_to(m)

    mapa_data = st_folium(m, height=800, use_container_width=True, key="mapa_galicia")

    if mapa_data["last_clicked"]:
        lat_c, lon_c = mapa_data["last_clicked"]["lat"], mapa_data["last_clicked"]["lng"]
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
                        if pixel[0][0] != src.nodata: punto_valido = True
            except Exception: pass 
            
            if punto_valido:
                st.session_state['foco_ignicion'] = clicked_coords
                st.session_state['ultimo_click_invalido'] = None
                st.session_state['erro_incombustible'] = False 
                st.rerun()
            else:
                st.session_state['ultimo_click_invalido'] = clicked_coords
                st.toast("❌ Localización inválida.", icon="🚫")