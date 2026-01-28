import time
import numpy as np
import rasterio
from rasterio.windows import from_bounds
import folium
from folium import Icon
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
from skimage.graph import MCP_Geometric
from skimage import measure
from pyproj import Transformer

from script_04_meteo import consultar_vento_api

# ---------------- MOTOR DE PROPAGACIÓN ----------------

def simular_incendio(ignicion_coords, horas_sim, usar_manual, v_velocidad, v_direccion, v_humedad, api_key, FICHEIRO_MDT, FICHEIRO_COMBUSTIBLE):

    start_time = time.time()
    RADIO_SIMULACION_METROS = int(horas_sim * 2500)

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

    # ---------------- LÓXICA METEOROLÓXICA ----------------

    fallback_activo = False
    if usar_manual:
        rad = np.radians((v_direccion + 180) % 360)
        U_v = np.full_like(elev, v_velocidad * np.sin(rad))
        V_v = np.full_like(elev, v_velocidad * np.cos(rad))
        rh_ambiente, v_rep = v_humedad, v_velocidad
    else:
        v_data, err = consultar_vento_api(api_key, w_bounds, crs_raster)
        if err:
            fallback_activo = True
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

    # ---------------- FÍSICA E ROTHERMEL ----------------

    dy, dx = np.gradient(elev, cell_size)
    slp, asp = np.arctan(np.sqrt(dx**2 + dy**2)), np.arctan2(-dx, dy)
    Phi_S = 5.275 * (np.tan(slp)**2)
    Sx, Sy = Phi_S * np.sin(asp + np.pi), Phi_S * np.cos(asp + np.pi)
    
    V_R0 = {0:0, 1:15, 2:20, 3:25, 4:25, 5:12, 6:10, 7:8, 8:4, 9:3.5, 10:5, 11:3, 12:8, 13:12}
    R0 = np.zeros_like(fuel, dtype=float)
    for m, v in V_R0.items(): R0[fuel == m] = v
    
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

    # ---------------- MCP E ISÓCRONAS ----------------
    
    mcp = MCP_Geometric(cost)
    tiempos, _ = mcp.find_costs(starts=[(py_local, px_local)])
    tiempos = np.where(tiempos >= 1e8, np.nan, tiempos)
    tiempos[tiempos > (horas_sim * 60)] = np.nan 

    max_mins = np.nanmax(tiempos)
    
    if max_mins <= 0:
        return None, None, True, fallback_activo # Erro incombustible

    ha = np.count_nonzero(~np.isnan(tiempos)) * (cell_size**2) / 10000.0
    
    t_w84 = Transformer.from_crs(crs_raster, "EPSG:4326", always_xy=True)
    if hasattr(w_bounds, 'left'): w_l, w_b, w_r, w_t = w_bounds.left, w_bounds.bottom, w_bounds.right, w_bounds.top
    else: w_l, w_b, w_r, w_t = w_bounds
        
    l_w, b_w = t_w84.transform(w_l, w_b)
    r_w, t_w = t_w84.transform(w_r, w_t)
    b_latlon = [[b_w, l_w], [t_w, r_w]]

    rgba = plt.get_cmap('YlOrRd')(mcolors.Normalize(vmin=0, vmax=max_mins)(tiempos))
    rgba[np.isnan(tiempos), 3] = 0  
    
    m_res = folium.Map(location=[ignicion_coords[0], ignicion_coords[1]], zoom_start=13, min_zoom=6, tiles='OpenTopoMap')
    folium.raster_layers.ImageOverlay(image=rgba, bounds=b_latlon, opacity=0.4).add_to(m_res)

    for n in np.arange(60 if max_mins > 120 else 15, max_mins, 60 if max_mins > 120 else 15):
        for c in measure.find_contours(tiempos, n):
            pts = [[t_w84.transform(*(w_trans * (col, fil)))[1], t_w84.transform(*(w_trans * (col, fil)))[0]] for fil, col in c]
            folium.PolyLine(locations=pts, color='red', weight=2.5, tooltip=f"{int(n)} min").add_to(m_res)

    folium.Marker(location=ignicion_coords, icon=Icon(color='black', icon='fire', prefix='fa')).add_to(m_res)
    
    tempo_exec = time.time() - start_time
    print(f"\n SIMULACIÓN REMATADA ({horas_sim} HORAS) | Tempo: {tempo_exec:.4f} seg")
    
    kpis = (ha, max_mins, v_rep, rh_ambiente)
    return m_res, kpis, False, fallback_activo