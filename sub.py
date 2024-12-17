# Importaciones principales
import streamlit as st
import requests
import pandas as pd
import base64
import time
from datetime import datetime

# Importamos BeautifulSoup con manejo de errores
try:
    from bs4 import BeautifulSoup
except ImportError:
    st.error("Error al importar BeautifulSoup4. Por favor, verifica que beautifulsoup4 está instalado correctamente.")
    st.stop()

# Importamos Google API con manejo de errores
try:
    from googleapiclient.discovery import build
except ImportError:
    st.error("Error al importar Google API Client. Por favor, verifica la instalación.")
    st.stop()

# Configuración de la página
st.set_page_config(
    page_title="Transcriptor de YouTube Shorts",
    page_icon="🎥",
    layout="wide"
)

# Estilo CSS personalizado
st.markdown("""
    <style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .stButton>button {
        width: 100%;
    }
    .success-message {
        padding: 1rem;
        background-color: #d4edda;
        border-color: #c3e6cb;
        color: #155724;
        border-radius: 0.25rem;
        margin-bottom: 1rem;
    }
    .error-message {
        padding: 1rem;
        background-color: #f8d7da;
        border-color: #f5c6cb;
        color: #721c24;
        border-radius: 0.25rem;
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)  # Caché por 1 hora
def obtener_shorts_del_canal(api_key, channel_id):
    """
    Obtiene la lista de Shorts de un canal de YouTube utilizando la API oficial.
    
    Parámetros:
        api_key (str): Clave de API de YouTube
        channel_id (str): ID del canal de YouTube
    
    Retorna:
        list: Lista de diccionarios con información de los Shorts
    """
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        shorts_info = []
        
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            maxResults=50,
            type="video"
        )
        
        while request and len(shorts_info) < 50:
            response = request.execute()
            
            for item in response['items']:
                video_id = item['id']['videoId']
                
                # Obtener detalles del video para verificar duración
                video_response = youtube.videos().list(
                    part='contentDetails,statistics',
                    id=video_id
                ).execute()
                
                if 'items' in video_response:
                    duration = video_response['items'][0]['contentDetails']['duration']
                    # Verificar si es un Short (duración menor a 1 minuto)
                    if 'M' not in duration or int(duration.split('M')[0].replace('PT', '')) < 1:
                        shorts_info.append({
                            'video_id': video_id,
                            'title': item['snippet']['title'],
                            'url': f'https://www.youtube.com/shorts/{video_id}'
                        })
            
            request = youtube.search().list_next(request, response)
            
        return shorts_info
    except Exception as e:
        st.error(f"Error al obtener los Shorts: {str(e)}")
        return []

@st.cache_data(ttl=600)  # Caché por 10 minutos
def generar_transcripcion(url):
    """
    Genera la transcripción de un Short utilizando Downsub.
    
    Parámetros:
        url (str): URL del Short de YouTube
    
    Retorna:
        str: Texto de la transcripción o None si hay error
    """
    try:
        session = requests.Session()
        
        # Obtener el token CSRF
        response = session.get('https://downsub.com/')
        if not response.ok:
            st.warning(f"Error al conectar con Downsub: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.text, 'lxml')  # Usamos lxml como parser
        csrf_token = soup.find('input', {'name': '_token'})
        
        if not csrf_token or 'value' not in csrf_token.attrs:
            st.warning("No se pudo obtener el token CSRF")
            return None
            
        # Solicitar la transcripción
        data = {
            '_token': csrf_token['value'],
            'url': url,
            'type': 'auto'
        }
        
        response = session.post('https://downsub.com/api/extract', data=data)
        if response.ok:
            json_data = response.json()
            if 'data' in json_data and json_data['data']:
                transcript_url = json_data['data'][0].get('url')
                if transcript_url:
                    transcript_response = session.get(transcript_url)
                    if transcript_response.ok:
                        return transcript_response.text.strip()
        
        return None
    except Exception as e:
        st.error(f"Error al generar la transcripción: {str(e)}")
        return None

def get_download_link(df):
    """
    Crea un enlace de descarga para el DataFrame en formato CSV.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f'<a href="data:file/csv;base64,{b64}" download="transcripciones_{fecha}.csv">📥 Descargar transcripciones (CSV)</a>'

def main():
    """
    Función principal que maneja la interfaz de usuario y el flujo de la aplicación.
    """
    st.title("🎥 Transcriptor de YouTube Shorts")
    
    st.markdown("""
    ### 📝 Instrucciones:
    1. Obtén tu API Key en [Google Cloud Console](https://console.cloud.google.com)
    2. Activa YouTube Data API v3 en tu proyecto
    3. Copia el ID del canal de YouTube (está en la URL del canal)
    4. Ingresa los datos abajo y haz clic en "Generar Transcripciones"
    """)
    
    # Formulario de entrada
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input(
                "API Key de YouTube",
                type="password",
                help="Tu clave de API de Google Cloud"
            )
        with col2:
            channel_id = st.text_input(
                "ID del Canal",
                help="El ID que aparece en la URL del canal"
            )
        
        max_shorts = st.slider(
            "Número de Shorts a procesar",
            min_value=1,
            max_value=50,
            value=10,
            help="Selecciona cuántos Shorts quieres procesar"
        )
        
        submitted = st.form_submit_button("🚀 Generar Transcripciones")
    
    if submitted:
        if not api_key or not channel_id:
            st.error("❌ Por favor, ingresa tanto la API Key como el ID del canal.")
            return
        
        with st.spinner("🔍 Buscando Shorts en el canal..."):
            shorts_info = obtener_shorts_del_canal(api_key, channel_id)
            
            if not shorts_info:
                st.error("❌ No se encontraron Shorts en este canal o hubo un error.")
                return
            
            shorts_info = shorts_info[:max_shorts]
            results_df = pd.DataFrame(columns=['Video ID', 'Título', 'URL', 'Transcripción'])
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, short in enumerate(shorts_info):
                status_text.text(f"⏳ Procesando Short {i+1}/{len(shorts_info)}")
                
                transcript = generar_transcripcion(short['url'])
                
                new_row = pd.DataFrame([{
                    'Video ID': short['video_id'],
                    'Título': short['title'],
                    'URL': short['url'],
                    'Transcripción': transcript if transcript else 'No se pudo generar la transcripción'
                }])
                
                results_df = pd.concat([results_df, new_row], ignore_index=True)
                progress_bar.progress((i + 1) / len(shorts_info))
                time.sleep(1)
            
            st.success("✅ ¡Proceso completado!")
            
            # Mostrar resultados
            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Enlace de descarga
            st.markdown(get_download_link(results_df), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
