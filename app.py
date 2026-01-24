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
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Recuperamos los secretos
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client.open("db_usuarios_app").sheet1
        else:
            st.error("No se encontraron los secretos de Google Cloud.")
            return None
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None

def hash_password(password):
    # Limpiamos espacios antes de encriptar para evitar errores tontos
    clean_pass = str(password).strip()
    return hashlib.sha256(str.encode(clean_pass)).hexdigest()

def cargar_usuarios():
    sheet = conectar_db()
    if sheet:
        try:
            data = sheet.get_all_records()
            users_dict = {}
            for row in data:
                # CORRECCIÓN CRÍTICA: Forzamos que el usuario sea texto (String) y minúsculas
                # Esto evita errores si Google Sheets piensa que "123" es un número.
                u_key = str(row['username']).strip()
                users_dict[u_key] = row
            return users_dict
        except Exception as e:
            st.error(f"Error leyendo usuarios: {e}")
            return {}
    return {}

def crear_usuario_nuevo(username, password, nombre, apellido, email, rol):
    sheet = conectar_db()
    if not sheet: return False, "Error de conexión."
    
    # Validaciones básicas
    username = str(username).strip()
    if not username or not password:
        return False, "Usuario y contraseña no pueden estar vacíos."

    # Descargar usuarios actuales para verificar duplicados
    users = cargar_usuarios()
    if username in users:
        return False, "El usuario ya existe."
    
    try:
        # Guardar nueva fila
        nueva_fila = [username, nombre, apellido, email, hash_password(password), rol]
        sheet.append_row(nueva_fila)
        return True, "Usuario guardado en Google Sheets exitosamente."
    except Exception as e:
        return False, f"Error escribiendo en la hoja: {e}"

def eliminar_usuario(username):
    sheet = conectar_db()
    if not sheet: return False
    try:
        cell = sheet.find(username)
        sheet.delete_row(cell.row)
        return True
    except:
        return False

# --- 2. CONEXIÓN MERCADOLIBRE ---

def obtener_token_ml():
    # Verificamos si tenemos las credenciales antes de intentar
    if "mercadolibre" not in st.secrets:
        return None # Aún no configurado

    try:
        url = "https://api.mercadolibre.com/oauth/token"
        headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'client_credentials',
            'client_id': st.secrets["mercadolibre"]["app_id"],
            'client_secret': st.secrets["mercadolibre"]["client_secret"]
        }
        r = requests.post(url, headers=headers, data=data)
        if r.status_code == 200:
            return r.json()['access_token']
        return None
    except:
        return None

def buscar_productos(query):
    token = obtener_token_ml()
    
    url = f"https://api.mercadolibre.com/sites/MLC/search"
    params = {'q': query, 'limit': 20}
    headers = {}
    if token:
        headers = {'Authorization': f'Bearer {token}'}
    
    try:
        r = requests.get(url, params=params, headers=headers)
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
                        "Vendedor": item.get("seller", {}).get("nickname", "N/A"),
                        "¿Oferta?": oferta,
                        "Enlace": item.get("permalink")
                    })
                return pd.DataFrame(resultados)
    except:
        pass

    # Fallback Demo si falla la API
    st.warning("⚠️ No se pudo conectar con MercadoLibre (Verificar credenciales). Mostrando DEMO.")
    return pd.DataFrame([{"Imagen": "https://via.placeholder.com/150", "Producto": f"Demo {query}", "Precio": "$999", "Vendedor": "Demo", "Enlace": "#"}])

# --- 3. INTERFAZ PRINCIPAL ---
def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # PANTALLA DE LOGIN
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Login")
            u_input = st.text_input("Usuario")
            p_input = st.text_input("Contraseña", type="password")
            
            if st.button("Ingresar"):
                u_clean = str(u_input).strip()
                p_clean = str(p_input).strip()

                # 1. PUERTA TRASERA DE EMERGENCIA (Siempre funciona)
                # Esto te permite entrar aunque la base de datos falle o no tenga al admin
                if u_clean == "admin" and p_clean == "admin123":
                    st.success("Accediendo como Super Admin (Modo Emergencia)...")
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"nombre": "Super", "apellido": "Admin", "rol": "admin", "username": "admin"}
                    st.rerun()

                # 2. LOGIN NORMAL (Base de Datos)
                users = cargar_usuarios()
                
                # Verificamos credenciales
                if u_clean in users:
                    stored_pass = users[u_clean]["password"]
                    input_pass_hash = hash_password(p_clean)
                    
                    if stored_pass == input_pass_hash:
                        st.session_state.logged_in = True
                        st.session_state.user_info = users[u_clean]
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta.")
                else:
                    st.error("Usuario no encontrado.")
        return

    # APLICACIÓN LOGUEADA
    user = st.session_state.user_info
    
    with st.sidebar:
        st.write(f"👤 **{user.get('nombre', 'Usuario')}**")
        st.caption(f"Rol: {user.get('rol')}")
        
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.rerun()
        
        opcion = "Buscador"
        if user.get("rol") == "admin":
            st.divider()
            opcion = st.radio("Menú", ["Buscador", "Usuarios (Admin)"])

    if opcion == "Buscador":
        st.title("🔎 Comparador")
        q = st.text_input("Buscar producto:")
        if st.button("Buscar") and q:
            df = buscar_productos(q)
            st.data_editor(df, column_config={"Imagen": st.column_config.ImageColumn()}, use_container_width=True)

    elif opcion == "Usuarios (Admin)":
        st.title("👥 Gestión de Usuarios")
        st.info("Nota: Si creas un usuario 'admin', este quedará guardado permanentemente en la hoja.")
        
        with st.form("new_user"):
            c1, c2 = st.columns(2)
            nu = c1.text_input("Usuario (Login)").strip()
            np = c2.text_input("Contraseña", type="password").strip()
            nn = c1.text_input("Nombre")
            na = c2.text_input("Apellido")
            ne = st.text_input("Email")
            nr = st.selectbox("Rol", ["user", "admin"])
            
            if st.form_submit_button("Crear Usuario"):
                ok, msg = crear_usuario_nuevo(nu, np, nn, na, ne, nr)
                if ok: st.success(msg)
                else: st.error(msg)
        
        st.write("---")
        st.subheader("Usuarios en Base de Datos")
        st.dataframe(pd.DataFrame(cargar_usuarios().values()))

if __name__ == "__main__":
    main()