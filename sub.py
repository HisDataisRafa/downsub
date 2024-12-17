import streamlit as st
import requests
import pandas as pd
import base64
import time
from datetime import datetime
import json
import html
from urllib.parse import urlencode

# Configuración inicial de la página
st.set_page_config(page_title="Transcriptor de YouTube Shorts", page_icon="🎥", layout="wide")

# Manejo de la importación de la API de YouTube
def init_youtube_api():
    try:
        # Intentamos importar las bibliotecas necesarias en el orden correcto
        from googleapiclient import discovery
        # Creamos una función de construcción del servicio que podemos usar más tarde
        def build_youtube_service(api_key):
            return discovery.build('youtube', 'v3', developerKey=api_key)
        return True, build_youtube_service
    except Exception as e:
        return False, str(e)

# Inicializamos la API y guardamos el resultado
YOUTUBE_API_AVAILABLE, youtube_service_builder = init_youtube_api()

if not YOUTUBE_API_AVAILABLE:
    st.error("No se pudo inicializar la API de YouTube. Por favor, contacta al administrador.")

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
    </style>
""", unsafe_allow_html=True)

def obtener_shorts_del_canal(api_key, channel_id):
    """
    Obtiene la lista de Shorts de un canal de YouTube.
    """
    if not YOUTUBE_API_AVAILABLE:
        st.error("La API de YouTube no está disponible.")
        return []
        
    try:
        # Construimos el servicio de YouTube usando nuestra función guardada
        youtube = youtube_service_builder(api_key)
        shorts_info = []
        
        # Solicitamos los videos del canal
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
                video_response = youtube.videos().list(
                    part='contentDetails',
                    id=video_id
                ).execute()
                
                if 'items' in video_response and video_response['items']:
                    duration = video_response['items'][0]['contentDetails']['duration']
                    # Verificamos si es un Short por su duración
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

@st.cache_data(ttl=600)
def generar_transcripcion(url):
    """
    Genera la transcripción de un Short usando Downsub.
    """
    try:
        session = requests.Session()
        
        # Obtenemos la página inicial de Downsub
        response = session.get('https://downsub.com/')
        if not response.ok:
            return None
            
        # Extraemos el token CSRF
        content = response.text
        token_start = content.find('name="_token" value="') + 20
        token_end = content.find('"', token_start)
        csrf_token = content[token_start:token_end]
        
        if not csrf_token:
            return None
        
        # Configuramos la solicitud para la transcripción
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        data = {
            '_token': csrf_token,
            'url': url,
            'type': 'auto'
        }
        
        # Solicitamos la transcripción
        response = session.post(
            'https://downsub.com/api/extract',
            data=data,
            headers=headers
        )
        
        if response.ok:
            json_data = response.json()
            if json_data.get('data') and json_data['data']:
                transcript_url = json_data['data'][0].get('url')
                if transcript_url:
                    transcript_response = session.get(transcript_url)
                    if transcript_response.ok:
                        text = transcript_response.text
                        text = html.unescape(text)
                        return '\n'.join(line for line in text.splitlines() if line.strip())
        
        return None
    except Exception as e:
        st.error(f"Error en la transcripción: {str(e)}")
        return None

def get_download_link(df):
    """
    Crea un enlace para descargar los resultados en CSV.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f'<a href="data:file/csv;base64,{b64}" download="transcripciones_{fecha}.csv">📥 Descargar transcripciones (CSV)</a>'

def main():
    """
    Función principal que maneja la interfaz y el flujo de la aplicación.
    """
    st.title("🎥 Transcriptor de YouTube Shorts")
    
    if not YOUTUBE_API_AVAILABLE:
        st.warning("La aplicación está en modo limitado debido a problemas con la API de YouTube.")
    
    st.markdown("""
    Esta aplicación genera transcripciones automáticas para los Shorts de un canal de YouTube.
    
    ### 📝 Instrucciones:
    1. Obtén tu API Key en la [Google Cloud Console](https://console.cloud.google.com)
    2. Activa YouTube Data API v3 en tu proyecto
    3. Ingresa el ID del canal (lo encuentras en la URL del canal)
    4. Selecciona cuántos Shorts quieres procesar
    """)
    
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input(
                "API Key de YouTube",
                type="password",
                help="Tu API Key de Google Cloud"
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
            value=10
        )
        
        submitted = st.form_submit_button("🚀 Generar Transcripciones")
    
    if submitted:
        if not api_key or not channel_id:
            st.error("❌ Por favor, ingresa tanto la API Key como el ID del canal.")
            return
        
        with st.spinner("🔍 Buscando Shorts..."):
            shorts_info = obtener_shorts_del_canal(api_key, channel_id)
            
            if not shorts_info:
                st.error("❌ No se encontraron Shorts o hubo un error.")
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
                    'Transcripción': transcript if transcript else 'No se pudo generar transcripción'
                }])
                
                results_df = pd.concat([results_df, new_row], ignore_index=True)
                progress_bar.progress((i + 1) / len(shorts_info))
                time.sleep(1)
            
            st.success("✅ ¡Proceso completado!")
            
            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown(get_download_link(results_df), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
