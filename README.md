# Simulador de Incendios en Galicia

Este repositorio contén o código fonte dun **Simulador Xeoespacial Web** para a predición da propagación de incendios forestais no territorio galego. O proxecto foi desenvolvido como **Traballo de Fin de Máster (TFM)**.

A aplicación atópase despregada e plenamente funcional a través de:

**[Simulador de Incendios en Galicia](https://simulador-lumes-galicia.streamlit.app/)**

---

##  Características Principais

* **Modelo Físico Avanzado:** Adaptación continua das ecuacións de **Rothermel** combinadas con variables meteorolóxicas en tempo real.
* **Eficiencia Computacional:** Resolución en cuestión de segundos a escala autonómica grazas á discretización do espazo.
* **Operatividade Dual (Clima):**
  * **Modo Dinámico:** Inxestión automatizada de variables meteorolóxicas en tempo real a través da API de **MeteoGalicia**.
  * **Modo Manual:** Permite configurar manualmente as condicións de vento e humidade para simular escenarios hipotéticos ou históricos.
* **Deseño Responsivo:** Interface interactiva adaptada e optimizada tanto para pantallas de escritorio como para dispositivos móbiles (teléfonos e tabletas).

---

## 🛠️ Arquitectura do Sistema

O proxecto segue unha estrutura modular que separa a lóxica de negocio, o motor analítico e a interface gráfica:

* `dashboard_completo.py`: Punto de entrada da aplicación. Xestiona a interface de usuario, os estados de sesión de Streamlit e a renderización de mapas cartográficos.
* `script_05_motor.py`: Núcleo analítico do simulador. Executa as ecuacións físicas de Rothermel e o procesamento das matrices espaciais co algoritmo MCP.
* `script_04_meteo.py`: Módulo encargado do consumo, análise e transformación de datos meteorolóxicos da API de MeteoGalicia.
* `style.css`: Ficheiro de estilos encargado de garantir a adaptabilidade responsiva da interface.

---

## 📦 Instalación Local

### 1. Clonar o repositorio
```bash
git clone https://github.com/manuel-ramos-ll/simulador-incendios-galicia
cd simulador-incendios-galicia
```

### 2. Instalar dependencias xeoespaciais
Este proxecto require bibliotecas analíticas complexas (`rasterio`, `scikit-image`, `folium`, etc.).

Instala os requisitos de Python:
```bash
pip install -r requirements.txt
```

### 3. Ficheiros de Datos (MDT e Combustibles)
Para o correcto funcionamento do sistema, precísanse os mapas mestres de Galicia a 25 metros de resolución:
* `Combustibles_Galicia_25m.tif`: Debe estar na raíz do proxecto xunto aos scripts.
* `MDT_Galicia_25m.tif`: O sistema inclúe unha rutina de inicio condicional que o descargará de forma automática dende un servidor externo na súa primeira execución se non o atopa localmente.

---

## 💻 Execución

Para lanzar o servidor local de Streamlit e interactuar co *Dashboard*, executa:

```bash
streamlit run dashboard_completo.py
```

A aplicación abrirase automaticamente no teu navegador na dirección `http://localhost:8501`.
