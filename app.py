from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sadeco_secret_key_123'

# Configuración Base de Datos (PostgreSQL en Nube / SQLite en Local)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///sadeco_workers.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CONFIGURACIÓN SIMPLE DE SEGURIDAD ---
# En un entorno real, esto iría en variables de entorno
ADMIN_PASSWORD = "sadeco"  # <--- CONTRASEÑA DE ACCESO
# app.secret_key = 'llave_secreta_sadeco_super_segura' # Ya se usa app.config['SECRET_KEY']

# --- PROTECTOR DE ACCESO (MIDDLEWARE) ---
@app.before_request
def require_login():
    # Rutas permitidas sin contraseña (login, estáticos, etc)
    allowed_routes = ['login', 'static', 'manifest']
    if request.endpoint and request.endpoint not in allowed_routes and 'logged_in' not in session:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = "Contraseña incorrecta"
    
    return """
    <html>
        <head>
            <title>Acceso Restringido</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background: #00703C; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; }
                .card { max-width: 400px; width: 90%; padding: 20px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }
                .btn-sadeco { background: #FDB913; color: black; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="card text-center">
                <h3 class="mb-4">🔐 Capataz SADECO</h3>
                <p class="text-muted">Área restringida a personal autorizado</p>
                <form method="post">
                    <input type="password" name="password" class="form-control form-control-lg mb-3" placeholder="Contraseña de acceso" required autofocus>
                    <button type="submit" class="btn btn-sadeco btn-lg w-100">Entrar</button>
                    {% if error %}<p class="text-danger mt-3">{{ error }}</p>{% endif %}
                </form>
            </div>
        </body>
    </html>
    """, 200

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# --- MODELO DE DATOS ---
class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Peón, Conductor, etc.
    
    # Antigüedad (para calcular vacaciones según convenio)
    years_worked = db.Column(db.Integer, default=0)  # Años trabajados en la empresa
    
    # Saldos Disponibles (Se pueden ajustar individualmente)
    vacation_days = db.Column(db.Integer, default=22) # Días laborables por defecto
    personal_days = db.Column(db.Integer, default=6)  # Asuntos propios (Moscosos)
    extra_hours = db.Column(db.Float, default=0.0)    # Horas acumuladas positivas
    
    # Control de Bajas Médicas
    is_sick = db.Column(db.Boolean, default=False)
    sick_start = db.Column(db.DateTime, nullable=True)
    total_sick_days = db.Column(db.Integer, default=0)
    
    # Historial de Notas (Para apuntar "pidió el día tal por WhatsApp")
    logs = db.relationship('Log', backref='worker', lazy=True)
    
    def calculate_vacation_days(self):
        """Calcula días de vacaciones según antigüedad (convenio SADECO)"""
        base_days = 22  # Base para todos
        
        # Según convenio colectivo de limpieza:
        # 15-20 años: +1 día (23 días)
        # 20-25 años: +2 días (24 días)
        # 25+ años: +3 días (25 días)
        
        if self.years_worked >= 25:
            return base_days + 3
        elif self.years_worked >= 20:
            return base_days + 2
        elif self.years_worked >= 15:
            return base_days + 1
        else:
            return base_days

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    action = db.Column(db.String(50)) # "Restar Vacaciones", "Sumar Horas", etc.
    amount = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(200))

# Crear tablas y manejar migraciones de esquema
with app.app_context():
    try:
        db.create_all()
        # Intentar agregar columnas faltantes si la tabla ya existe
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        if 'worker' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('worker')]
            
            # Agregar columnas faltantes si no existen
            if 'is_sick' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN is_sick BOOLEAN DEFAULT 0'))
                    conn.commit()
            
            if 'sick_start' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN sick_start DATETIME'))
                    conn.commit()
                    
            if 'total_sick_days' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN total_sick_days INTEGER DEFAULT 0'))
                    conn.commit()
                    
            if 'years_worked' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE worker ADD COLUMN years_worked INTEGER DEFAULT 0'))
                    conn.commit()
    except Exception as e:
        print(f"Error en migración de base de datos: {e}")
        # Continuar de todos modos para que la app arranque


# --- CATEGORIAS ---
CATEGORIES = [
    "Peón Limpiador de Colegios",
    "Peón Limpieza Viaria", 
    "Conductor Recogida",
    "Oficial de Mantenimiento",
    "Administrativo"
]

# --- CEREBRO DEL CONVENIO (Knowledge Base) ---
CONVENIO_RULES = {
    "vacaciones": {"dias": "22 + Antigüedad", "desc": "22 días laborables base. +1 día con 15 años, +2 días con 20 años, +3 días con 25+ años."},
    "asuntos_propios": {"dias": 6, "desc": "6 días de libre disposición (Moscosos). No acumulables a vacaciones."},
    "matrimonio": {"dias": 20, "desc": "20 días naturales por matrimonio o registro pareja de hecho."},
    "nacimiento": {"dias": 3, "desc": "3 días (o 5 si hay desplazamiento fuera de la provincia)."},
    
    "fallecimiento_1_local": {"dias": 3, "desc": "Fallecimiento o Enf. Grave 1º Grado (Padres, Hijos, Cónyuge) en LOCALIDAD."},
    "fallecimiento_1_fuera": {"dias": 5, "desc": "Fallecimiento o Enf. Grave 1º Grado con DESPLAZAMIENTO."},
    
    "fallecimiento_2_local": {"dias": 2, "desc": "Fallecimiento o Enf. Grave 2º Grado (Abuelos, Nietos, Hermanos) en LOCALIDAD."},
    "fallecimiento_2_fuera": {"dias": 4, "desc": "Fallecimiento o Enf. Grave 2º Grado con DESPLAZAMIENTO."},
    
    "mudanza": {"dias": 1, "desc": "1 día por traslado de domicilio habitual."},
    "deber_inexcusable": {"dias": "Variable", "desc": "El tiempo indispensable para el cumplimiento (Juicios, Voto, Mesa electoral)."},
    "medico": {"dias": "Variable", "desc": "El tiempo indispensable para consulta médica especialista (Seguridad Social)."}
}

def analyze_worker_status(worker):
    """Mini-IA que analiza la situación del trabajador"""
    insights = []
    
    # Análisis SALUD (Nuevo)
    if worker.is_sick and worker.sick_start:
        days_sick = (datetime.utcnow() - worker.sick_start).days
        insights.append({"type": "danger", "msg": f"🚑 DE BAJA desde hace {days_sick} días."})
    
    # Análisis Vacaciones
    pct_vac = (22 - worker.vacation_days) / 22 * 100
    if worker.vacation_days > 15 and datetime.utcnow().month > 9:
        insights.append({"type": "warning", "msg": "⚠️ Acumulación de vacaciones peligrosa para fin de año."})
    elif worker.vacation_days == 0:
        insights.append({"type": "success", "msg": "✅ Vacaciones completadas."})

    # Análisis Asuntos Propios
    if worker.personal_days < 0:
        insights.append({"type": "danger", "msg": f"🔴 Exceso en Asuntos Propios: Debe {abs(worker.personal_days)} días."})
    
    # Análisis Horas
    if worker.extra_hours > 80:
        insights.append({"type": "warning", "msg": "⚠️ La bolsa de horas es muy alta (+80h). Revisar descansos."})

    return insights

# --- RUTAS ACTUALIZADAS ---
@app.route('/')
def index():
    search = request.args.get('search', '')
    if search:
        workers = Worker.query.filter(Worker.name.contains(search)).all()
    else:
        workers = Worker.query.all()
    
    # Estadística Global para el Capataz
    total_workers = len(workers)
    # Estadísticas Bajas
    sick_workers = sum(1 for w in workers if w.is_sick)
    absenteeism_rate = round((sick_workers / total_workers * 100), 1) if total_workers > 0 else 0
    
    if total_workers > 0:
        avg_vac_left = sum(w.vacation_days for w in workers) / total_workers
    else:
        avg_vac_left = 0
        
    global_stats = {
        "total": total_workers,
        "sick": sick_workers,
        "sick_rate": absenteeism_rate,
        "avg_vac": round(avg_vac_left, 1),
        "alerts": sum(1 for w in workers if w.vacation_days < 0 or w.personal_days < 0)
    }

    return render_template('index.html', workers=workers, categories=CATEGORIES, stats=global_stats)

@app.route('/worker/<int:id>')
def worker_detail(id):
    worker = Worker.query.get_or_404(id)
    insights = analyze_worker_status(worker) # La IA analiza al trabajador
    return render_template('worker_detail.html', worker=worker, insights=insights, rules=CONVENIO_RULES)

@app.route('/convenio')
def convenio_view():
    return render_template('convenio.html', rules=CONVENIO_RULES)

@app.route('/update/<int:id>', methods=['POST'])
def update_worker(id):
    worker = Worker.query.get_or_404(id)
    type_action = request.form.get('type') # 'vacation', 'personal', 'hours', 'sick_leave'
    operation = request.form.get('operation') # 'add', 'subtract', 'start', 'end'
    amount = float(request.form.get('amount', 1))
    note = request.form.get('note', '')
    
    action_text = "Actualización"

    if type_action == 'vacation':
        if operation == 'subtract':
            worker.vacation_days -= int(amount)
            action_text = "Disfrute Vacaciones"
        else:
            worker.vacation_days += int(amount)
            action_text = "Ajuste Vacaciones (+)"
            
    elif type_action == 'personal':
        if operation == 'subtract':
            worker.personal_days -= int(amount)
            action_text = "Uso Asuntos Propios"
        else:
            worker.personal_days += int(amount)
            action_text = "Ajuste Asuntos Propios (+)"

    elif type_action == 'hours':
        if operation == 'add':
            worker.extra_hours += amount
            action_text = "Acumula Horas Extra"
        else:
            worker.extra_hours -= amount
            action_text = "Uso de Horas Acumuladas"
            
    elif type_action == 'sick_leave':
        if operation == 'start':
            if not worker.is_sick:
                worker.is_sick = True
                worker.sick_start = datetime.utcnow()
                action_text = "🚑 BAJA MÉDICA INICIADA"
        elif operation == 'end':
            if worker.is_sick:
                days = (datetime.utcnow() - worker.sick_start).days
                worker.is_sick = False
                worker.total_sick_days += days
                worker.sick_start = None
                action_text = f"✅ ALTA MÉDICA (Duración: {days} días)"

    # Guardar Log
    new_log = Log(worker_id=worker.id, action=action_text, amount=amount if type_action != 'sick_leave' else 0, notes=note)
    db.session.add(new_log)
    db.session.commit()
    
    flash(f'Actualizado correctamente: {worker.name}', 'success')
    return redirect(url_for('worker_detail', id=worker.id))

@app.route('/add_worker', methods=['POST'])
def add_worker():
    name = request.form.get('name')
    category = request.form.get('category')
    
    # Antigüedad
    try:
        years = int(request.form.get('years_worked', 0))
    except:
        years = 0
        
    # Moscosos (por defecto 6)
    try:
        pers = int(request.form.get('personal_days', 6))
    except:
        pers = 6

    # Vacaciones: Si viene vacío, calcular AUTO
    vac_input = request.form.get('vacation_days', '')
    if vac_input and vac_input.strip():
        try:
            vacs = int(vac_input)
        except:
            vacs = 22
    else:
        # Cálculo automático según antigüedad
        temp_worker = Worker(years_worked=years)
        vacs = temp_worker.calculate_vacation_days()

    new_worker = Worker(
        name=name, 
        category=category, 
        years_worked=years,
        vacation_days=vacs, 
        personal_days=pers
    )
    db.session.add(new_worker)
    db.session.commit()
    flash(f'Trabajador creado: {name} (Antigüedad: {years} años -> {vacs} días vacs.)', 'success')
    return redirect(url_for('index'))

import re  # Importar módulo de expresiones regulares

# ... imports existentes ...

@app.route('/import_workers', methods=['POST'])
def import_workers():
    """
    Importación INTELIGENTE masiva.
    Detecta patrones en texto pegado (Excel, PDF, CSV desordenado).
    Busca: Nombre, Antigüedad (años o fecha), Categoría.
    """
    raw_text = request.form.get('csv_data', '')
    lines = raw_text.strip().split('\n')
    count = 0
    
    # Patrones Inteligentes (Regex)
    # 1. Detectar años: "15 años", "20 a", "Antigüedad: 10"
    regex_years = r'(\d+)\s*(?:años|a\.|anys|a)'
    # 2. Detectar fechas: 12/05/1990, 1990-05-12
    regex_date = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    
    for line in lines:
        if not line.strip(): continue
        
        parts = line.split(',')
        
        # --- ESTRATEGIA DE EXTRACCIÓN ---
        name = "Desconocido"
        years = 0
        category = "Peón Limpieza Viaria" # Default
        vacs = 22 # Base
        pers = 6
        
        # A) Intento CSV simple (Nombre, Años/Antigüedad)
        if len(parts) >= 2 and parts[1].strip().isdigit():
            name = parts[0].strip()
            years = int(parts[1].strip())
            
        # B) Intento Inteligente (Texto libre / Excel pegado)
        else:
            # 1. Buscar Nombre (asumimos que es lo primero que no es número ni fecha)
            # Limpiamos caracteres extraños
            clean_line = line.replace('\t', ' ').strip()
            
            # 2. Buscar Años explícitos
            match_years = re.search(regex_years, clean_line, re.IGNORECASE)
            if match_years:
                years = int(match_years.group(1))
            
            # 3. Buscar fechas para calcular antigüedad si no hay años explícitos
            elif re.search(regex_date, clean_line):
                match_date = re.search(regex_date, clean_line)
                date_str = match_date.group(1)
                try:
                    # Intentar parsar fecha (asumiendo dd/mm/yyyy)
                    from datetime import datetime
                    fmt = "%d/%m/%Y" if '/' in date_str else "%Y-%m-%d"
                    start_date = datetime.strptime(date_str, fmt)
                    # Calcular años hasta hoy
                    today = datetime.now()
                    years = today.year - start_date.year - ((today.month, today.day) < (start_date.month, start_date.day))
                except:
                    years = 0 # Fallback si falla fecha
            
            # 4. Inferir nombre (todo lo que está antes de los números)
            # Esto es heurístico, asumimos que el nombre va al principio
            name_match = re.search(r'^([a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+)', clean_line)
            if name_match:
                name = name_match.group(1).strip()
            else:
                name = parts[0].strip() # Fallback al primer trozo
            
            # 5. Detectar Categoría por palabras clave
            line_lower = clean_line.lower()
            if "conductor" in line_lower: category = "Conductor Recogida"
            elif "colegios" in line_lower: category = "Peón Limpiador de Colegios"
            elif "mantenimiento" in line_lower or "oficial" in line_lower: category = "Oficial de Mantenimiento"
            elif "administrativo" in line_lower: category = "Administrativo"
            
        # --- CÁLCULO DE VACACIONES ---
        # Usamos un Worker temporal para calcular
        temp_worker = Worker(years_worked=years)
        vacs = temp_worker.calculate_vacation_days()
        
        # --- GUARDAR EN BD ---
        if name and len(name) > 3: # Evitar guardar basura
            new_w = Worker(
                name=name, 
                category=category, 
                years_worked=years,
                vacation_days=vacs, 
                personal_days=pers
            )
            db.session.add(new_w)
            count += 1
            
    db.session.commit()
    flash(f'Importación INTELIGENTE completada: {count} trabajadores añadidos.', 'success')
    return redirect(url_for('index'))

@app.route('/init_db')
def init_db():
    db.drop_all() # ¡Importante! Borra lo viejo para meter los nuevos campos
    db.create_all()
    # Datos de demostración
    w1 = Worker(name="Manuel Pérez (Veterano)", category="Peón Limpiador de Colegios", years_worked=26) # +3 días
    w1.vacation_days = w1.calculate_vacation_days() # 25 días
    
    w2 = Worker(name="Antonio Obrero (Medio)", category="Peón Limpieza Viaria", years_worked=16) # +1 día
    w2.vacation_days = w2.calculate_vacation_days() # 23 días
    
    w3 = Worker(name="Luisa Conductora (Nueva)", category="Conductor Recogida", years_worked=2) # Base
    w3.vacation_days = w3.calculate_vacation_days() # 22 días
    
    db.session.add_all([w1, w2, w3])
    db.session.commit()
    return "Base de datos REINICIADA con estructura de Bajas + Antigüedad + Importación Inteligente."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
