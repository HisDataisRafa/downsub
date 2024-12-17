# Importaciones básicas necesarias para el funcionamiento de la aplicación
import streamlit as st
import requests
import pandas as pd
import base64
import time
from datetime import datetime
import json
import html
from urllib.parse import urlencode
import os
import sys

# Configuración inicial de la página de Streamlit
st.set_page_config(
    page_title="Transcriptor de YouTube Shorts",
    page_icon="🎥",
    layout="wide"
)

# Intentamos importar las bibliotecas de Google con manejo detallado de errores
try:
    st.info("Inicializando la API de Google...")
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import google.oauth2.credentials
    import google_auth_oauthlib.flow
    GOOGLE_API_AVAILABLE = True
    st.success("✅ API de Google inicializada correctamente")
except ImportError as e:
    GOOGLE_API_AVAILABLE = False
    error_message = f"""
    ❌ Error al importar las bibliotecas de Google API.
    
    Detalles del error: {str(e)}
    
    Por favor, asegúrate de que el archivo requirements.txt contiene:
    - google-api-python-client==2.108.0
    - google-auth-httplib2==0.1.1
    - google-auth-oauthlib==1.1.0
    - oauth2client==4.1.3
    - protobuf==4.24.4
    
    Estado actual del sistema:
    - Python version: {sys.version}
    - Directorio actual: {os.getcwd()}
    """
    st.error(error_message)
    st.stop()

# Estilo CSS personalizado para mejorar la apariencia de la aplicación
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

@st.cache_data(ttl=3600)  # Cache por 1 hora para optimizar el rendimiento
def obtener_shorts_del_canal(api_key, channel_id):
    """
    Obtiene la lista de Shorts de un canal de YouTube usando la API oficial.
    Incluye manejo de errores mejorado y verificación de duración para identificar Shorts.
    """
    if not GOOGLE_API_AVAILABLE:
        st.error("La API de Google no está disponible. Por favor, verifica la instalación.")
        return []
        
    try:
        # Inicialización del servicio de YouTube
        youtube = build('youtube', 'v3', developerKey=api_key)
        shorts_info = []
        
        # Configuración de la solicitud inicial
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            maxResults=50,
            type="video"
        )
        
        # Bucle para obtener todos los videos hasta el límite
        while request and len(shorts_info) < 50:
            try:
                response = request.execute()
                
                # Verificación de errores en la respuesta
                if 'error' in response:
                    error_msg = response['error'].get('message', 'Error desconocido de API')
                    st.error(f"Error de API de YouTube: {error_msg}")
                    return []
                
                # Procesamiento de cada video encontrado
                for item in response['items']:
                    video_id = item['id']['videoId']
                    try:
                        # Obtener detalles adicionales del video
                        video_response = youtube.videos().list(
                            part='contentDetails,statistics',
                            id=video_id
                        ).execute()
                        
                        # Verificar si es un Short basado en la duración
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
                
                # Preparar la siguiente página de resultados
                request = youtube.search().list_next(request, response)
                
            except HttpError as e:
                # Manejo de errores específicos de la API
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

@st.cache_data(ttl=600)  # Cache por 10 minutos
def generar_transcripcion(url):
    """
    Genera la transcripción de un Short utilizando el servicio de Downsub.
    Implementa un método directo para obtener y procesar la transcripción.
    """
    try:
        # Inicializar sesión para mantener cookies y headers
        session = requests.Session()
        
        # Primera solicitud para obtener el token CSRF
        response = session.get('https://downsub.com/')
        if not response.ok:
            st.warning(f"Error de conexión con Downsub: {response.status_code}")
            return None
        
        # Extraer el token CSRF del HTML
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
        
        # Procesar la respuesta
        if extract_response.ok:
            json_data = extract_response.json()
            if json_data.get('data') and len(json_data['data']) > 0:
                transcript_url = json_data['data'][0].get('url')
                if transcript_url:
                    # Obtener y procesar la transcripción
                    transcript_response = session.get(transcript_url)
                    if transcript_response.ok:
                        text = transcript_response.text
                        text = html.unescape(text)  # Decodificar entidades HTML
                        text = '\n'.join(line for line in text.splitlines() if line.strip())
                        return text
        
        return None
    except Exception as e:
        st.error(f"Error en la generación de transcripción: {str(e)}")
        return None

def get_download_link(df):
    """
    Crea un enlace de descarga para el DataFrame en formato CSV.
    Incluye la fecha y hora en el nombre del archivo.
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
    
    # Instrucciones para el usuario
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
    
    # Procesamiento cuando se envía el formulario
    if submitted:
        if not api_key or not channel_id:
            st.error("❌ Por favor, ingresa tanto la API Key como el ID del canal.")
            return
        
        with st.spinner("🔍 Buscando Shorts en el canal..."):
            shorts_info = obtener_shorts_del_canal(api_key, channel_id)
            
            if not shorts_info:
                st.error("❌ No se encontraron Shorts en este canal o hubo un error.")
                return
            
            # Limitar al número seleccionado por el usuario
            shorts_info = shorts_info[:max_shorts]
            results_df = pd.DataFrame(columns=['Video ID', 'Título', 'URL', 'Transcripción'])
            
            # Configurar elementos de progreso
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Procesar cada Short
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
                time.sleep(1)  # Pausa para evitar sobrecarga
            
            st.success("✅ ¡Proceso completado!")
            
            # Mostrar resultados en una tabla
            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Proporcionar enlace de descarga
            st.markdown(get_download_link(results_df), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
