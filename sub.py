# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
import time
import pandas as pd
import json
import base64
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="YouTube Shorts Transcriber",
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

def obtener_shorts_del_canal(api_key, channel_id):
    """
    Obtiene los URLs de todos los Shorts de un canal de YouTube.
    """
    youtube = build('youtube', 'v3', developerKey=api_key)
    shorts_info = []
    
    try:
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            maxResults=50,
            type="video"
        )
        
        while request:
            response = request.execute()
            
            for item in response['items']:
                video_id = item['id']['videoId']
                # Verificar si es un Short checando la duración
                video_response = youtube.videos().list(
                    part='contentDetails,statistics',
                    id=video_id
                ).execute()
                
                if 'items' in video_response:
                    duration = video_response['items'][0]['contentDetails']['duration']
                    # Los Shorts suelen durar menos de 1 minuto
                    if 'M' not in duration or int(duration.split('M')[0].replace('PT', '')) < 1:
                        shorts_info.append({
                            'video_id': video_id,
                            'title': item['snippet']['title'],
                            'url': f'https://www.youtube.com/shorts/{video_id}',
                            'thumbnail': item['snippet']['thumbnails']['high']['url'],
                            'views': video_response['items'][0]['statistics'].get('viewCount', '0')
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
        # Primera solicitud a Downsub
        session = requests.Session()
        response = session.get('https://downsub.com/')
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Obtener el token CSRF
        csrf_token = soup.find('input', {'name': '_token'})['value']
        
        # Preparar los datos para la solicitud de generación
        data = {
            '_token': csrf_token,
            'url': url,
            'type': 'auto'
        }
        
        # Realizar la solicitud de generación
        response = session.post('https://downsub.com/api/extract', data=data)
        if not response.ok:
            return None
        
        # Procesar la respuesta
        json_data = response.json()
        if 'data' in json_data and json_data['data']:
            # Obtener el texto de la transcripción
            transcript_url = json_data['data'][0].get('url')
            if transcript_url:
                transcript_response = session.get(transcript_url)
                return transcript_response.text
        
        return None
    except Exception as e:
        st.error(f"Error al generar la transcripción: {str(e)}")
        return None

def get_table_download_link(df, filename):
    """
    Genera un enlace de descarga para el DataFrame.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Descargar CSV</a>'
    return href

def main():
    st.title("🎥 Generador de Transcripciones para YouTube Shorts")
    st.write("Esta aplicación genera transcripciones automáticas para YouTube Shorts de un canal específico.")
    
    # Campos de entrada
    with st.form("input_form"):
        api_key = st.text_input("API Key de YouTube", type="password")
        channel_id = st.text_input("ID del Canal de YouTube")
        max_shorts = st.number_input("Número máximo de Shorts a procesar", min_value=1, max_value=50, value=10)
        submitted = st.form_submit_button("Generar Transcripciones")
    
    if submitted and api_key and channel_id:
        with st.spinner("Obteniendo lista de Shorts..."):
            shorts_info = obtener_shorts_del_canal(api_key, channel_id)
            
            if not shorts_info:
                st.error("No se encontraron Shorts en este canal o hubo un error al obtenerlos.")
                return
            
            # Limitar el número de Shorts según la entrada del usuario
            shorts_info = shorts_info[:max_shorts]
            
            # Crear DataFrame para almacenar resultados
            results_df = pd.DataFrame(columns=['Video ID', 'Título', 'URL', 'Transcripción'])
            
            # Mostrar progreso
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, short in enumerate(shorts_info):
                status_text.text(f"Procesando Short {i+1}/{len(shorts_info)}: {short['title']}")
                
                # Generar transcripción
                transcript = generar_transcripcion(short['url'])
                
                # Actualizar DataFrame
                results_df = pd.concat([results_df, pd.DataFrame([{
                    'Video ID': short['video_id'],
                    'Título': short['title'],
                    'URL': short['url'],
                    'Transcripción': transcript if transcript else 'Error al generar transcripción'
                }])], ignore_index=True)
                
                # Actualizar barra de progreso
                progress_bar.progress((i + 1) / len(shorts_info))
                time.sleep(1)  # Pequeña pausa entre requests
            
            # Mostrar resultados
            st.success("¡Proceso completado!")
            st.dataframe(results_df)
            
            # Generar enlace de descarga
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transcripciones_shorts_{timestamp}.csv"
            st.markdown(get_table_download_link(results_df, filename), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
