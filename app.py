import streamlit as st
import pandas as pd
import requests
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Comparador ML Pro", page_icon="🛍️", layout="wide")

# --- 1. CONEXIÓN BASE DE DATOS (GOOGLE SHEETS) ---
def conectar_db():
    try:
        if "gcp_service_account" not in st.secrets:
            # Fallo silencioso si no hay config de google, para no romper la app visualmente
            return None

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("db_usuarios_app").sheet1
    except Exception as e:
        print(f"Advertencia DB: {e}")
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
    if not sheet: return False, "Error de conexión con Base de Datos."
    
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

# --- 2. MOTOR DE BÚSQUEDA HÍBRIDO ---

def obtener_token_ml():
    """Genera el pase temporal para leer precios reales."""
    if "mercadolibre" not in st.secrets:
        return None

    url = "https://api.mercadolibre.com/oauth/token"
    headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'client_credentials',
        'client_id': st.secrets["mercadolibre"]["app_id"],
        'client_secret': st.secrets["mercadolibre"]["client_secret"]
    }
    
    try:
        r = requests.post(url, headers=headers, data=data)
        if r.status_code == 200:
            return r.json()['access_token']
        return None
    except:
        return None

def busqueda_anonima_fallback(query):
    """
    Intento desesperado: Si el token falla (403), intentamos buscar
    como si fueramos un navegador normal para salvar la consulta.
    """
    url = "https://api.mercadolibre.com/sites/MLC/search"
    # Lista de navegadores para rotar y evitar bloqueos
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/118.0"
    ]
    
    params = {'q': query, 'limit': 20}
    headers = {'User-Agent': random.choice(user_agents)}
    
    try:
        r = requests.get(url, params=params, headers=headers)
        if r.status_code == 200:
            return procesar_resultados(r.json())
    except:
        pass
    return pd.DataFrame()

def procesar_resultados(data):
    """Convierte el JSON de ML en una tabla limpia."""
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

def buscar_productos(query):
    # ESTRATEGIA 1: INTENTO OFICIAL (CON TOKEN)
    token = obtener_token_ml()
    
    if token:
        url = "https://api.mercadolibre.com/sites/MLC/search"
        headers = {'Authorization': f'Bearer {token}'}
        params = {'q': query, 'limit': 20}
        
        try:
            r = requests.get(url, headers=headers, params=params)
            
            if r.status_code == 200:
                return procesar_resultados(r.json())
            elif r.status_code == 403:
                st.warning("⚠️ Permiso denegado con Token Oficial (Revisar checkbox 'Negocios' en ML). Intentando ruta alternativa...")
                # Si falla por permisos, saltamos a la ESTRATEGIA 2
                return busqueda_anonima_fallback(query)
            else:
                st.error(f"Error MercadoLibre: {r.status_code}")
        except Exception as e:
            st.error(f"Error técnico: {e}")
    
    # ESTRATEGIA 2: INTENTO ANÓNIMO (Si no hay token o falló)
    df = busqueda_anonima_fallback(query)
    if not df.empty:
        return df

    # ESTRATEGIA 3: MODO DEMO (Último recurso si todo falla)
    st.info("Mostrando DEMO (No se pudo conectar).")
    return pd.DataFrame([{"Imagen": "https://via.placeholder.com/150", "Producto": f"DEMO {query}", "Precio": "$0", "Vendedor": "Sistema", "Enlace": "#"}])

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
                if u.strip() == "admin" and p.strip() == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"nombre": "Super Admin", "rol": "admin"}
                    st.rerun()
                
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
                elif df.empty:
                     st.warning("No se encontraron resultados.")

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