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

# --- 2. MOTOR DE BÚSQUEDA (MODO NAVEGADOR) ---
# Esta versión NO usa el Token que da error 403.
# Simula ser un navegador real para ver precios públicos.

def buscar_productos(query):
    url = "https://api.mercadolibre.com/sites/MLC/search"
    params = {'q': query, 'limit': 20}
    
    # Rotación de identidades (User-Agents) para evitar bloqueos
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    
    # Elegimos uno al azar
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'application/json'
    }
    
    try:
        # Hacemos la petición SIN token (Anónima)
        r = requests.get(url, headers=headers, params=params)
        
        if r.status_code == 200:
            data = r.json()
            resultados = []
            if "results" in data:
                for item in data["results"]:
                    precio = item.get("price")
                    original = item.get("original_price")
                    oferta = "SÍ" if original and precio < original else "NO"
                    # Mejoramos la calidad de la imagen (de I a O)
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
        else:
            # Si falla, mostramos el código para entender qué pasó
            st.error(f"Error de conexión ({r.status_code})")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- 3. INTERFAZ ---

def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Login
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Acceso")
            u = st.text_input("Usuario")
            p = st.text_input("Pass", type="password")
            if st.button("Entrar"):
                # Backdoor Admin
                if u.strip() == "admin" and p.strip() == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"nombre": "Admin", "rol": "admin"}
                    st.rerun()
                
                # Login Real
                users = cargar_usuarios()
                u_cl = u.strip()
                if u_cl in users and users[u_cl]["password"] == hash_password(p):
                    st.session_state.logged_in = True
                    st.session_state.user_info = users[u_cl]
                    st.rerun()
                else:
                    st.error("Error de acceso")
        return

    # App Principal
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
            with st.spinner("Buscando mejores precios..."):
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
                    st.warning("No se encontraron resultados o hubo un bloqueo temporal.")

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