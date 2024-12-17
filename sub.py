import streamlit as st
import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
import time
import pandas as pd
import base64
from datetime import datetime

# Configuración inicial de la página
st.set_page_config(
    page_title="Transcriptor de YouTube Shorts",
    page_icon="🎥",
    layout="wide"
)

# Estilo personalizado
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
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        shorts_info = []
        
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            maxResults=50,
            type="video"
        )
        
        while request and len(shorts_info) < 50:  # Límite de 50 shorts
            response = request.execute()
            
            for item in response['items']:
                video_id = item['id']['videoId']
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

def generar_transcripcion(url):
    """
    Genera la transcripción de un Short usando Downsub.
    """
    try:
        session = requests.Session()
        
        # Primera solicitud para obtener el token CSRF
        response = session.get('https://downsub.com/')
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_token = soup.find('input', {'name': '_token'})['value']
        
        # Solicitar la transcripción
        data = {
            '_token': csrf_token,
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
                    return transcript_response.text
        
        return None
    except Exception as e:
        st.error(f"Error al generar la transcripción: {str(e)}")
        return None

def get_download_link(df):
    """
    Crea un enlace de descarga para el DataFrame.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f'<a href="data:file/csv;base64,{b64}" download="transcripciones_{fecha}.csv">📥 Descargar transcripciones (CSV)</a>'

def main():
    st.title("🎥 Transcriptor de YouTube Shorts")
    
    st.markdown("""
    Esta aplicación te permite generar transcripciones automáticas para los Shorts de un canal de YouTube.
    
    ### 📝 Instrucciones:
    1. Ingresa tu API Key de YouTube
    2. Ingresa el ID del canal
    3. Selecciona cuántos Shorts quieres procesar
    """)
    
    # Formulario de entrada
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input("API Key de YouTube", type="password", help="Obtén tu API Key en Google Cloud Console")
        with col2:
            channel_id = st.text_input("ID del Canal", help="El ID que aparece en la URL del canal")
        
        max_shorts = st.slider("Número de Shorts a procesar", 1, 50, 10)
        submitted = st.form_submit_button("🚀 Generar Transcripciones")
    
    if submitted and api_key and channel_id:
        with st.spinner("🔍 Buscando Shorts en el canal..."):
            shorts_info = obtener_shorts_del_canal(api_key, channel_id)
            
            if not shorts_info:
                st.error("❌ No se encontraron Shorts en este canal o hubo un error.")
                return
            
            shorts_info = shorts_info[:max_shorts]
            results_df = pd.DataFrame(columns=['Video ID', 'Título', 'URL', 'Transcripción'])
            
            # Barra de progreso
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, short in enumerate(shorts_info):
                status_text.text(f"⏳ Procesando Short {i+1}/{len(shorts_info)}")
                
                transcript = generar_transcripcion(short['url'])
                
                new_row = pd.DataFrame([{
                    'Video ID': short['video_id'],
                    'Título': short['title'],
                    'URL': short['url'],
                    'Transcripción': transcript if transcript else 'Error al generar transcripción'
                }])
                
                results_df = pd.concat([results_df, new_row], ignore_index=True)
                progress_bar.progress((i + 1) / len(shorts_info))
                time.sleep(1)  # Pausa para evitar sobrecarga
            
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
