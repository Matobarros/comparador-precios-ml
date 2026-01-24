import streamlit as st
import pandas as pd
import requests
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Comparador ML Pro", page_icon="☁️", layout="wide")

# --- CONEXIÓN BASE DE DATOS (GOOGLE SHEETS) ---
def conectar_db():
    """Conecta con Google Sheets usando los Secretos de Streamlit."""
    try:
        # Recuperamos los secretos configurados en la nube
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Convertimos el objeto de secretos de Streamlit a un diccionario normal
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abre la hoja por nombre (Asegúrate que se llame así en tu Google Drive)
        sheet = client.open("db_usuarios_app").sheet1
        return sheet
    except Exception as e:
        st.error(f"Error conectando a la Base de Datos: {e}")
        return None

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def cargar_usuarios():
    """Descarga los usuarios desde la Hoja de Cálculo."""
    sheet = conectar_db()
    if sheet:
        data = sheet.get_all_records()
        # Convertimos la lista de filas a un diccionario para que sea fácil de buscar
        users_dict = {}
        for row in data:
            users_dict[row['username']] = row
        
        # Si la hoja está vacía, creamos el admin en memoria para poder entrar la primera vez
        if not users_dict:
            return {"admin": {"nombre": "Admin", "password": hash_password("admin123"), "rol": "admin"}}
            
        return users_dict
    return {}

def crear_usuario_nuevo(username, password, nombre, apellido, email, rol):
    sheet = conectar_db()
    if not sheet: return False, "Error de conexión."
    
    # Verificar si existe descargando la columna de usernames
    usernames = sheet.col_values(1) # Columna A
    if username in usernames:
        return False, "El usuario ya existe."
    
    # Agregar nueva fila
    nueva_fila = [username, nombre, apellido, email, hash_password(password), rol]
    sheet.append_row(nueva_fila)
    return True, "Usuario guardado en la nube exitosamente."

def eliminar_usuario(username):
    sheet = conectar_db()
    if not sheet: return False
    
    # Buscamos la celda que contiene el username
    cell = sheet.find(username)
    if cell:
        sheet.delete_row(cell.row)
        return True
    return False

# --- MOTOR DE BÚSQUEDA (MODO DEMO POR AHORA) ---
def buscar_productos(query):
    # Intentamos conexión real
    url = f"https://api.mercadolibre.com/sites/MLC/search?q={query}&limit=10"
    try:
        r = requests.get(url, headers={"User-Agent": "Googlebot/2.1"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            res = []
            for i in data.get("results", []):
                res.append({
                    "Imagen": i.get("thumbnail", ""),
                    "Producto": i.get("title"),
                    "Precio": f"${i.get('price', 0):,.0f}",
                    "Vendedor": i.get("seller", {}).get("nickname", "N/A"),
                    "Enlace": i.get("permalink")
                })
            if res: return pd.DataFrame(res)
    except:
        pass
        
    # Fallback Demo
    st.warning(f"⚠️ Modo Demo (Bloqueo IP Nube).")
    img = "https://via.placeholder.com/100"
    return pd.DataFrame([
        {"Imagen": f"{img}/00F/FFF?text=Demo", "Producto": f"{query} Pro", "Precio": "$99.990", "Vendedor": "Tienda X", "Enlace": "#"},
        {"Imagen": f"{img}/F00/FFF?text=Demo", "Producto": f"{query} Lite", "Precio": "$49.990", "Vendedor": "Tienda Y", "Enlace": "#"}
    ])

# --- INTERFAZ ---
def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("☁️ Acceso Nube")
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.button("Entrar"):
                # Si es el primer login y la DB está vacía, permitimos admin/admin123
                if u == "admin" and p == "admin123":
                    # Chequeo especial de emergencia
                    users = cargar_usuarios()
                    if "admin" in users and users["admin"]["password"] == hash_password("admin123"):
                        st.session_state.logged_in = True
                        st.session_state.user_info = users["admin"]
                        st.rerun()
                
                users = cargar_usuarios()
                if u in users and users[u]["password"] == hash_password(p):
                    st.session_state.logged_in = True
                    st.session_state.user_info = users[u]
                    st.rerun()
                else:
                    st.error("Credenciales inválidas")
        return

    # App Principal
    user = st.session_state.user_info
    with st.sidebar:
        st.write(f"Hola, **{user.get('nombre', 'Usuario')}**")
        if st.button("Salir"):
            st.session_state.logged_in = False
            st.rerun()
        
        opcion = "Buscador"
        if user.get("rol") == "admin":
            st.divider()
            opcion = st.radio("Menú Admin", ["Buscador", "Usuarios Cloud"])

    if opcion == "Buscador":
        st.title("🔎 Buscador Global")
        q = st.text_input("Buscar:")
        if st.button("Buscar") and q:
            st.data_editor(buscar_productos(q), use_container_width=True)

    elif opcion == "Usuarios Cloud":
        st.title("👥 Gestión Base de Datos")
        st.info("Estos usuarios se guardan en tu Google Sheet.")
        
        with st.form("crear"):
            c1, c2 = st.columns(2)
            nu = c1.text_input("Usuario (Login)")
            np = c2.text_input("Contraseña", type="password")
            nn = c1.text_input("Nombre")
            na = c2.text_input("Apellido")
            ne = st.text_input("Email")
            nr = st.selectbox("Rol", ["user", "admin"])
            if st.form_submit_button("Guardar en Nube"):
                ok, msg = crear_usuario_nuevo(nu, np, nn, na, ne, nr)
                if ok: st.success(msg)
                else: st.error(msg)
        
        st.write("---")
        st.subheader("Usuarios Actuales")
        st.dataframe(pd.DataFrame(cargar_usuarios().values()))

if __name__ == "__main__":
    main()