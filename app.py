import streamlit as st
import pandas as pd
import requests
import json
import os
import hashlib

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Comparador ML Seguro", page_icon="🔐", layout="wide")

# Archivo donde guardaremos los usuarios
DB_FILE = "usuarios.json"

# --- 1. SISTEMA DE SEGURIDAD Y USUARIOS (BACKEND) ---

def hash_password(password):
    """Convierte la contraseña en un código encriptado (SHA256)."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def cargar_usuarios():
    """Carga la base de datos de usuarios. Si no existe, crea al Admin por defecto."""
    if not os.path.exists(DB_FILE):
        # Creamos el usuario ADMIN por defecto
        users = {
            "admin": {
                "nombre": "Administrador",
                "apellido": "Sistema",
                "email": "admin@empresa.com",
                "password": hash_password("admin123"), # Contraseña inicial
                "rol": "admin"
            }
        }
        guardar_usuarios(users)
        return users
    else:
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}

def guardar_usuarios(users):
    """Guarda los cambios en el archivo json."""
    with open(DB_FILE, "w") as f:
        json.dump(users, f, indent=4)

def verificar_login(username, password):
    """Verifica si el usuario y contraseña coinciden."""
    users = cargar_usuarios()
    if username in users:
        # Comparamos la versión encriptada de la contraseña ingresada
        if users[username]["password"] == hash_password(password):
            return users[username]
    return None

def crear_usuario_nuevo(username, password, nombre, apellido, email, rol):
    """Función para que el Admin cree usuarios."""
    users = cargar_usuarios()
    if username in users:
        return False, "El nombre de usuario ya existe."
    
    users[username] = {
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
        "password": hash_password(password),
        "rol": rol
    }
    guardar_usuarios(users)
    return True, "Usuario creado exitosamente."

def eliminar_usuario(username):
    """Función para eliminar usuarios."""
    users = cargar_usuarios()
    if username in users:
        del users[username]
        guardar_usuarios(users)
        return True
    return False

# --- 2. MOTOR DE BÚSQUEDA (El que ya teníamos) ---

def generar_datos_simulados(busqueda):
    st.warning(f"⚠️ Modo Demo: Resultados simulados para '{busqueda}' (IP bloqueada temporalmente).")
    img_base = "https://via.placeholder.com/150"
    ejemplos = [
        {"Imagen": f"{img_base}/0000FF/FFFFFF?text=Prod+1", "Producto": f"{busqueda} Pro", "Precio": "$150.000", "Vendedor": "Tienda A", "Enlace": "#"},
        {"Imagen": f"{img_base}/008000/FFFFFF?text=Prod+2", "Producto": f"{busqueda} Lite", "Precio": "$90.000", "Vendedor": "Tienda B", "Enlace": "#"},
    ]
    return pd.DataFrame(ejemplos)

def buscar_productos(query):
    # Intentamos conexión real primero
    url = f"https://api.mercadolibre.com/sites/MLC/search?q={query}&limit=10"
    try:
        r = requests.get(url, headers={"User-Agent": "Chrome/120"}, timeout=5)
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
            return pd.DataFrame(res)
    except:
        pass
    return generar_datos_simulados(query)

# --- 3. INTERFAZ GRÁFICA (FRONTEND) ---

def main():
    # Inicializar estado de sesión (memoria de la app)
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_info = None

    # --- PANTALLA DE LOGIN ---
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Acceso Seguro")
            st.markdown("Bienvenido al Comparador de Precios Corporativo.")
            
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Ingresar"):
                user_data = verificar_login(username, password)
                if user_data:
                    st.session_state.logged_in = True
                    st.session_state.user_info = user_data
                    st.session_state.username_key = username # Guardamos el ID
                    st.rerun() # Recargamos la página para entrar
                else:
                    st.error("Usuario o contraseña incorrectos.")
        return # Detenemos la ejecución aquí si no está logueado

    # --- PANTALLA PRINCIPAL (SI YA ENTRÓ) ---
    
    # Barra lateral con información y menú
    user = st.session_state.user_info
    role = user.get("rol", "user")
    
    with st.sidebar:
        st.write(f"👤 **Hola, {user['nombre']} {user['apellido']}**")
        st.info(f"Rol: {role.upper()}")
        
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.rerun()
            
        st.divider()
        
        # MENÚ DE ADMINISTRADOR
        menu_seleccion = "Buscador"
        if role == "admin":
            st.header("⚙️ Panel Admin")
            menu_seleccion = st.radio("Ir a:", ["Buscador", "Gestionar Usuarios"])

    # Lógica de las pantallas
    if menu_seleccion == "Buscador":
        st.title("🔎 Comparador de MercadoLibre")
        busqueda = st.text_input("Ingresa producto, marca o EAN:")
        if st.button("Buscar") and busqueda:
            df = buscar_productos(busqueda)
            st.data_editor(
                df, 
                column_config={"Imagen": st.column_config.ImageColumn(), "Enlace": st.column_config.LinkColumn()}, 
                use_container_width=True
            )

    elif menu_seleccion == "Gestionar Usuarios":
        st.title("👥 Gestión de Usuarios")
        
        # Formulario para crear usuario
        with st.expander("➕ Crear Nuevo Usuario"):
            with st.form("new_user"):
                col_a, col_b = st.columns(2)
                new_user = col_a.text_input("Nombre de Usuario (Login)")
                new_pass = col_b.text_input("Contraseña", type="password")
                new_name = col_a.text_input("Nombre")
                new_last = col_b.text_input("Apellido")
                new_email = st.text_input("Correo Electrónico")
                new_role = st.selectbox("Perfil", ["user", "admin"])
                
                if st.form_submit_button("Crear Usuario"):
                    if new_user and new_pass and new_name and new_email:
                        ok, msg = crear_usuario_nuevo(new_user, new_pass, new_name, new_last, new_email, new_role)
                        if ok: st.success(msg)
                        else: st.error(msg)
                    else:
                        st.warning("Todos los campos son obligatorios.")

        # Tabla de usuarios existentes
        st.subheader("Lista de Usuarios Registrados")
        users_db = cargar_usuarios()
        
        # Convertimos el diccionario a tabla para visualizar
        lista_users = []
        for u_key, u_val in users_db.items():
            lista_users.append({
                "Usuario": u_key,
                "Nombre": f"{u_val['nombre']} {u_val['apellido']}",
                "Email": u_val['email'],
                "Rol": u_val['rol']
            })
        st.table(lista_users)
        
        # Eliminar usuario
        st.subheader("🗑️ Eliminar Usuario")
        user_to_delete = st.selectbox("Seleccionar usuario a eliminar", list(users_db.keys()))
        if st.button("Eliminar permanentemente"):
            if user_to_delete == st.session_state.username_key:
                st.error("¡No puedes eliminarte a ti mismo!")
            elif user_to_delete == "admin":
                st.error("No se puede eliminar al admin principal.")
            else:
                eliminar_usuario(user_to_delete)
                st.success(f"Usuario {user_to_delete} eliminado.")
                st.rerun()

if __name__ == "__main__":
    main()