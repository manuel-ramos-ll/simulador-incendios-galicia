import numpy as np
import requests
from pyproj import Transformer

# ---------------- CONSULTA METEOROLÓXICA ----------------

def consultar_vento_api(api_key, bounds, crs_raster):

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
    params = {"coords": coords_str, "variables": "wind,relative_humidity", "models": "WRF,WRF", "format": "application/json", "API_KEY": api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
    except Exception as e: 
        return None, f"Erro: {e}"

    if "exception" in data: 
        return None, f"Erro API: {data['exception']['message']}"
    
    puntos_u, puntos_v, puntos_rh, puntos_pos = [], [], [], []
    transformer_to_utm = Transformer.from_crs("EPSG:4326", crs_raster, always_xy=True)

    for feature in data['features']:
        if "exception" in feature: continue
        try:
            vel, direccion = 0.0, 0.0
            humidade_local = 65.0 
            
            for var in feature['properties']['days'][0]['variables']:
                if var['name'] == 'wind':
                    vel = var['values'][0]['moduleValue']
                    direccion = var['values'][0]['directionValue']
                elif var['name'] == 'relative_humidity':
                    humidade_local = var['values'][0]['value']
            
            lon_wgs, lat_wgs = feature['geometry']['coordinates']
            x_utm, y_utm = transformer_to_utm.transform(lon_wgs, lat_wgs)
            rad = np.radians((direccion + 180) % 360)
            puntos_u.append(vel * np.sin(rad))
            puntos_v.append(vel * np.cos(rad))
            puntos_rh.append(humidade_local)
            puntos_pos.append((x_utm, y_utm))
        except: 
            continue
    
    humidade_media = np.mean(puntos_rh) if puntos_rh else 65.0
    
    return (np.array(puntos_pos), puntos_u, puntos_v, humidade_media), None