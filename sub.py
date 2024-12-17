import streamlit as st
import requests
import pandas as pd
import base64
import time
from datetime import datetime
import json
import html
from urllib.parse import urlencode

# Importación de Google API con manejo de errores específicos
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError as e:
    GOOGLE_API_AVAILABLE = False
    st.error("""
    No se pudo importar la biblioteca de Google API. 
    Error específico: {}
    
    Por favor, verifica que el archivo requirements.txt contiene:
    google-api-python-client==2.108.0
    """.format(str(e)))
    st.stop()

# Configuración de la página
st.set_page_config(
    page_title="Transcriptor de YouTube Shorts",
    page_icon="🎥",
    layout="wide"
)

# Estilo CSS personalizado para mejorar la apariencia
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

@st.cache_data(ttl=3600)
def obtener_shorts_del_canal(api_key, channel_id):
    """
    Obtiene la lista de Shorts de un canal de YouTube utilizando la API oficial.
    Incluye manejo de errores mejorado para problemas comunes de API.
    """
    if not GOOGLE_API_AVAILABLE:
        st.error("La API de Google no está disponible. Por favor, verifica la instalación.")
        return []
        
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
            try:
                response = request.execute()
                
                if 'error' in response:
                    error_msg = response['error'].get('message', 'Error desconocido de API')
                    st.error(f"Error de API de YouTube: {error_msg}")
                    return []
                
                for item in response['items']:
                    video_id = item['id']['videoId']
                    try:
                        video_response = youtube.videos().list(
                            part='contentDetails,statistics',
                            id=video_id
                        ).execute()
                        
                        if 'items' in video_response and video_response['items']:
                            duration = video_response['items'][0]['contentDetails']['duration']
                            if 'M' not in duration or int(duration.split('M')[0].replace('PT', '')) < 1:
                                shorts_info.append({
                                    'video_id': video_id,
                                    'title': item['snippet']['title'],
                                    'url': f'https://www.youtube.com/shorts/{video_id}'
                                })
                    except HttpError as e:
                        st.warning(f"No se pudo obtener información del video {video_id}: {str(e)}")
                        continue
                
                request = youtube.search().list_next(request, response)
                
            except HttpError as e:
                if 'quota' in str(e).lower():
                    st.error("Se ha excedido la cuota de la API de YouTube. Por favor, inténtalo más tarde.")
                elif 'invalid' in str(e).lower():
                    st.error("La API Key proporcionada no es válida o ha expirado.")
                else:
                    st.error(f"Error al comunicarse con la API de YouTube: {str(e)}")
                return []
        
        return shorts_info
        
    except Exception as e:
        st.error(f"Error inesperado al obtener los Shorts: {str(e)}")
        return []

@st.cache_data(ttl=600)
def generar_transcripcion(url):
    """
    Genera la transcripción de un Short utilizando la API de Downsub.
    Implementa un método directo para obtener y procesar la transcripción.
    """
    try:
        session = requests.Session()
        
        # Primera solicitud para obtener la página y el token CSRF
        response = session.get('https://downsub.com/')
        if not response.ok:
            st.warning(f"Error de conexión: {response.status_code}")
            return None
        
        # Extraer el token CSRF
        content = response.text
        token_start = content.find('name="_token" value="') + 20
        token_end = content.find('"', token_start)
        csrf_token = content[token_start:token_end]
        
        if not csrf_token:
            st.warning("No se pudo obtener el token de autenticación")
            return None
        
        # Configurar headers para la solicitud de extracción
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # Preparar datos para la solicitud
        data = {
            '_token': csrf_token,
            'url': url,
            'type': 'auto'
        }
        
        # Realizar la solicitud de extracción
        extract_response = session.post(
            'https://downsub.com/api/extract',
            data=data,
            headers=headers
        )
        
        if extract_response.ok:
            json_data = extract_response.json()
            if json_data.get('data') and len(json_data['data']) > 0:
                transcript_url = json_data['data'][0].get('url')
                if transcript_url:
                    # Obtener y procesar la transcripción
                    transcript_response = session.get(transcript_url)
                    if transcript_response.ok:
                        text = transcript_response.text
                        text = html.unescape(text)
                        text = '\n'.join(line for line in text.splitlines() if line.strip())
                        return text
        
        return None
    except Exception as e:
        st.error(f"Error en la generación de transcripción: {str(e)}")
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
    Esta aplicación te permite generar transcripciones automáticas para los Shorts de un canal de YouTube.
    
    ### 📝 Instrucciones:
    1. Obtén tu API Key en la [Google Cloud Console](https://console.cloud.google.com)
    2. Asegúrate de habilitar YouTube Data API v3 en tu proyecto
    3. Ingresa el ID del canal (lo encuentras en la URL del canal)
    4. Selecciona cuántos Shorts quieres procesar
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
            
            # Proporcionar enlace de descarga
            st.markdown(get_download_link(results_df), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
