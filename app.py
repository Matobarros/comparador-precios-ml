import streamlit as st
import pandas as pd
import requests
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Comparador ML Pro", page_icon="🛍️", layout="wide")

# --- 1. CONEXIÓN BASE DE DATOS (GOOGLE SHEETS) ---
def conectar_db():
    try:
        # Verificamos si existen los secretos de Google
        if "gcp_service_account" not in st.secrets:
            st.error("Falta configuración de Google Sheets en Secrets.")
            return None

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # Abre la hoja. Asegúrate que en tu Google Drive se llame EXACTAMENTE así:
        return client.open("db_usuarios_app").sheet1
    except Exception as e:
        # Fallo silencioso para no bloquear la app si Google falla, pero logueamos
        print(f"Error DB: {e}") 
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
                # Convertimos username a string limpio y minúsculas
                u_key = str(row['username']).strip()
                users_dict[u_key] = row
            return users_dict
        except:
            pass
    return {}

def crear_usuario_nuevo(username, password, nombre, apellido, email, rol):
    sheet = conectar_db()
    if not sheet: return False, "Error de conexión con Google Sheets."
    
    username = str(username).strip()
    if not username or not password: return False, "Datos incompletos."
    
    users = cargar_usuarios()
    if username in users: return False, "El usuario ya existe."
    
    try:
        nueva_fila = [username, nombre, apellido, email, hash_password(password), rol]
        sheet.append_row(nueva_fila)
        return True, "Usuario creado exitosamente."
    except Exception as e:
        return False, f"Error técnico: {e}"

# --- 2. CONEXIÓN MERCADOLIBRE (OFICIAL) ---

def obtener_token_ml():
    """Genera el pase temporal para leer precios reales."""
    if "mercadolibre" not in st.secrets:
        st.error("Faltan las credenciales de MercadoLibre en Secrets.")
        return None

    url = "https://api.mercadolibre.com/oauth/token"
    headers = {
        'accept': 'application/json', 
        'content-type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'client_credentials',
        'client_id': st.secrets["mercadolibre"]["app_id"],
        'client_secret': st.secrets["mercadolibre"]["client_secret"]
    }
    
    try:
        r = requests.post(url, headers=headers, data=data)
        if r.status_code == 200:
            return r.json()['access_token']
        else:
            # Aquí mostramos el error real si MercadoLibre nos rechaza
            st.error(f"Error de Autenticación ML ({r.status_code}): {r.text}")
            return None
    except Exception as e:
        st.error(f"Error de conexión con ML: {e}")
        return None

def buscar_productos(query):
    token = obtener_token_ml()
    
    # Si no hay token, no podemos buscar precios reales
    if not token:
        st.warning("⚠️ Usando Modo Demo (No se pudo obtener Token Oficial).")
        return pd.DataFrame([{"Imagen": "https://via.placeholder.com/150", "Producto": "DEMO - Error Credenciales", "Precio": "$0", "Vendedor": "Sistema", "Enlace": "#"}])

    url = "https://api.mercadolibre.com/sites/MLC/search"
    headers = {'Authorization': f'Bearer {token}'}
    params = {'q': query, 'limit': 20}
    
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
                    foto = item.get("thumbnail", "").replace("http://", "https://")
                    
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
                st.info("No se encontraron resultados para esa búsqueda.")
                return pd.DataFrame()
        else:
            st.error(f"Error buscando productos ({r.status_code}): {r.text}")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error técnico buscando: {e}")
        return pd.DataFrame()

# --- 3. INTERFAZ ---

def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # LOGIN
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Acceso App")
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            
            if st.button("Ingresar"):
                # 1. Backdoor de emergencia (siempre funciona)
                if u.strip() == "admin" and p.strip() == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"nombre": "Super Admin", "rol": "admin"}
                    st.rerun()
                
                # 2. Login normal
                users = cargar_usuarios()
                u_clean = u.strip()
                if u_clean in users:
                    if users[u_clean]["password"] == hash_password(p):
                        st.session_state.logged_in = True
                        st.session_state.user_info = users[u_clean]
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta")
                else:
                    st.error("Usuario no encontrado")
        return

    # APP PRINCIPAL
    user = st.session_state.user_info
    
    with st.sidebar:
        st.write(f"Hola, **{user.get('nombre', 'Admin')}**")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.rerun()
        
        menu = "Buscador"
        if user.get("rol") == "admin":
            st.divider()
            menu = st.radio("Ir a:", ["Buscador", "Usuarios"])

    if menu == "Buscador":
        st.title("🔎 Buscador Oficial ML")
        q = st.text_input("Producto:")
        if st.button("Buscar") and q:
            with st.spinner("Conectando con MercadoLibre..."):
                df = buscar_productos(q)
                if not df.empty:
                    st.data_editor(
                        df, 
                        column_config={"Imagen": st.column_config.ImageColumn(), "Enlace": st.column_config.LinkColumn()}, 
                        use_container_width=True,
                        height=600
                    )

    elif menu == "Usuarios":
        st.title("👥 Gestión de Usuarios")
        with st.form("add_user"):
            c1, c2 = st.columns(2)
            nu = c1.text_input("Usuario")
            np = c2.text_input("Pass", type="password")
            nn = c1.text_input("Nombre")
            na = c2.text_input("Apellido")
            ne = st.text_input("Email")
            nr = st.selectbox("Rol", ["user", "admin"])
            if st.form_submit_button("Crear"):
                ok, msg = crear_usuario_nuevo(nu, np, nn, na, ne, nr)
                if ok: st.success(msg)
                else: st.error(msg)
        
        st.write("---")
        st.dataframe(pd.DataFrame(cargar_usuarios().values()))

if __name__ == "__main__":
    main()