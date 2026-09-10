import os
import re
from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

# Configuración del archivo Excel y columnas requeridas
EXCEL_PATH = 'Cursos_demo.xlsx'
REQUIRED_COLUMNS = {'DNI', 'Nombres', 'Curso', 'Fecha', 'Estado'}

def cargar_y_normalizar_padron():
    """
    Carga el padrón Excel en memoria RAM al iniciar la aplicación.
    Normaliza la columna DNI para garantizar la consistencia en las búsquedas.
    """
    if not os.path.exists(EXCEL_PATH):
        print(f"[ERROR CRÍTICO] El archivo {EXCEL_PATH} no fue encontrado.")
        # Retorna DataFrame vacío con la estructura esperada para prevenir caídas
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    try:
        df = pd.read_excel(EXCEL_PATH, dtype=str)
        
        # Validar presencia de columnas obligatorias
        if not REQUIRED_COLUMNS.issubset(df.columns):
            faltantes = REQUIRED_COLUMNS - set(df.columns)
            raise ValueError(f"Faltan columnas requeridas en el Excel: {faltantes}")

        # Limpieza de espacios y normalización de DNI a 8 dígitos con ceros a la izquierda
        df['DNI'] = df['DNI'].astype(str).str.strip().str.zfill(8)
        df['Nombres'] = df['Nombres'].astype(str).str.strip()
        df['Curso'] = df['Curso'].astype(str).str.strip()
        df['Fecha'] = df['Fecha'].astype(str).str.strip()
        df['Estado'] = df['Estado'].astype(str).str.strip()

        print(f"[INFO] Padrón SOMA cargado exitosamente. Total registros: {len(df)}")
        return df

    except Exception as e:
        print(f"[ERROR] Error al procesar el Excel: {str(e)}")
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

# Carga global en memoria RAM para evitar lecturas continuas en disco (Optimizando E/S y previniendo DoS)
DF_PADRON = cargar_y_normalizar_padron()

def normalizar_dni_entrada(dni_raw):
    """
    Valida y normaliza la entrada del usuario mediante Regex.
    Acepta de 6 a 8 dígitos y completa a 8 dígitos con zfill.
    """
    if not dni_raw:
        return None
    
    dni_limpio = str(dni_raw).strip()
    # Expresión regular estricta: entre 6 y 8 dígitos
    if re.fullmatch(r'\b\d{6,8}\b', dni_limpio):
        return dni_limpio.zfill(8)
    
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/buscar', methods=['POST'])
def buscar():
    """
    Endpoint para consulta de cursos por DNI.
    Soporta JSON o Form Data (QR o teclado).
    """
    data = request.get_json(silent=True) or request.form
    dni_input = data.get('dni')

    # Validar formato de entrada
    dni_normalizado = normalizar_dni_entrada(dni_input)
    if not dni_normalizado:
        return jsonify({
            'status': 'error',
            'code': 400,
            'message': 'DNI inválido. Debe contener entre 6 y 8 dígitos numéricos.'
        }), 400

    if DF_PADRON.empty:
        return jsonify({
            'status': 'error',
            'code': 500,
            'message': 'El padrón de cursos no está disponible en el servidor.'
        }), 500

    # Búsqueda eficiente en memoria
    resultados_df = DF_PADRON[DF_PADRON['DNI'] == dni_normalizado]

    if resultados_df.empty:
        # Estado HTTP 404/444 para registros no encontrados
        return jsonify({
            'status': 'not_found',
            'code': 444,
            'message': f'El DNI {dni_normalizado} no registra capacitaciones SOMA en el padrón.'
        }), 444

    # Extraer el nombre del trabajador (asumiendo consistencia en la primera coincidencia)
    nombre_trabajador = resultados_df['Nombres'].iloc[0]

    # Mapeo de cursos a diccionario ligero
    cursos = []
    tiene_vencido = False

    for _, row in resultados_df.iterrows():
        estado = row['Estado']
        if estado.upper() == 'VENCIDO':
            tiene_vencido = True
            
        cursos.append({
            'curso': row['Curso'],
            'fecha': row['Fecha'],
            'estado': estado
        })

    # Regla de Negocio: Semáforo Bipartito
    # Rojo: Si existe AL MENOS UN curso Vencido. Verde: Si todos son Aprobado/Pendiente.
    semaforo = 'ROJO' if tiene_vencido else 'VERDE'
    dictamen = 'NO CONFORME' if tiene_vencido else 'CONFORME'

    return jsonify({
        'status': 'success',
        'code': 200,
        'trabajador': {
            'nombre': nombre_trabajador,
            'dni': dni_normalizado,
            'semaforo': semaforo,
            'dictamen': dictamen
        },
        'cursos': cursos
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    