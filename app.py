import streamlit as st
import pandas as pd
import requests
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Comparador ML Pro", page_icon="🛍️", layout="wide")

# --- 1. BASE DE DATOS (GOOGLE SHEETS) ---
def conectar_db():
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("db_usuarios_app").sheet1
    except Exception as e:
        return None

def hash_password(password):
    return hashlib.sha256(str.encode(str(password).strip())).hexdigest()

def cargar_usuarios():
    sheet = conectar_db()
    if sheet:
        try:
            data = sheet.get_all_records()
            users_dict = {}
            for row in data:
                u_key = str(row['username']).strip()
                users_dict[u_key] = row
            return users_dict
        except:
            pass
    return {}

def crear_usuario_nuevo(username, password, nombre, apellido, email, rol):
    sheet = conectar_db()
    if not sheet: return False, "Error DB."
    username = str(username).strip()
    if not username or not password: return False, "Datos incompletos."
    users = cargar_usuarios()
    if username in users: return False, "Usuario existente."
    try:
        nueva_fila = [username, nombre, apellido, email, hash_password(password), rol]
        sheet.append_row(nueva_fila)
        return True, "Creado exitosamente."
    except Exception as e:
        return False, f"Error: {e}"

# --- 2. MOTOR DE BÚSQUEDA (CAMUFLAJE AVANZADO) ---

def buscar_productos(query):
    url = "https://api.mercadolibre.com/sites/MLC/search"
    params = {'q': query, 'limit': 20}
    
    # CAMUFLAJE: Simulamos ser un usuario real en Chile navegando desde Chrome
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
        'Referer': 'https://www.mercadolibre.cl/',
        'Origin': 'https://www.mercadolibre.cl',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }
    
    try:
        r = requests.get(url, headers=headers, params=params)
        
        if r.status_code == 200:
            data = r.json()
            resultados = []
            if "results" in data:
                for item in data["results"]:
                    precio = item.get("price")
                    original = item.get("original_price")
                    oferta = "SÍ" if original and precio < original else "NO"
                    foto = item.get("thumbnail", "").replace("http://", "https://").replace("-I.jpg", "-O.jpg")
                    
                    resultados.append({
                        "Imagen": foto,
                        "Producto": item.get("title"),
                        "Precio": f"${precio:,.0f}",
                        "Vendedor": item.get("seller", {}).get("nickname", "Desconocido"),
                        "¿Oferta?": oferta,
                        "Enlace": item.get("permalink")
                    })
            return pd.DataFrame(resultados)
            
        elif r.status_code == 403:
             st.error("🔒 Bloqueo de seguridad de MercadoLibre (IP Cloud). Intenta más tarde.")
             return pd.DataFrame()
        else:
            st.error(f"Error desconocido ({r.status_code})")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- 3. INTERFAZ ---

def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Acceso")
            u = st.text_input("Usuario")
            p = st.text_input("Pass", type="password")
            if st.button("Entrar"):
                if u.strip() == "admin" and p.strip() == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"nombre": "Admin", "rol": "admin"}
                    st.rerun()
                
                users = cargar_usuarios()
                u_cl = u.strip()
                if u_cl in users and users[u_cl]["password"] == hash_password(p):
                    st.session_state.logged_in = True
                    st.session_state.user_info = users[u_cl]
                    st.rerun()
                else:
                    st.error("Error de acceso")
        return

    user = st.session_state.user_info
    with st.sidebar:
        st.write(f"Hola, **{user.get('nombre', 'Admin')}**")
        if st.button("Salir"):
            st.session_state.logged_in = False
            st.rerun()
        
        menu = "Buscador"
        if user.get("rol") == "admin":
            st.divider()
            menu = st.radio("Ir a:", ["Buscador", "Usuarios"])

    if menu == "Buscador":
        st.title("🔎 Buscador ML")
        q = st.text_input("Producto:")
        if st.button("Buscar") and q:
            with st.spinner("Buscando..."):
                df = buscar_productos(q)
                if not df.empty:
                    st.data_editor(
                        df, 
                        column_config={
                            "Imagen": st.column_config.ImageColumn(width="small"), 
                            "Enlace": st.column_config.LinkColumn()
                        }, 
                        height=700, 
                        use_container_width=True
                    )
                else:
                    # Si falla, mostramos un mensaje amigable
                    if not st.session_state.get("error_shown"):
                        st.warning("No se encontraron resultados.")

    elif menu == "Usuarios":
        st.title("👥 Usuarios")
        with st.form("new"):
            c1, c2 = st.columns(2)
            nu = c1.text_input("User")
            np = c2.text_input("Pass")
            nn = c1.text_input("Nombre")
            ne = st.text_input("Email")
            nr = st.selectbox("Rol", ["user", "admin"])
            if st.form_submit_button("Guardar"):
                ok, msg = crear_usuario_nuevo(nu, np, nn, "", ne, nr)
                if ok: st.success(msg)
                else: st.error(msg)
        st.dataframe(pd.DataFrame(cargar_usuarios().values()))

if __name__ == "__main__":
    main()