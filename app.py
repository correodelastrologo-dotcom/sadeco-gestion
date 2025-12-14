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

# --- MODELO DE DATOS ---
class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Peón, Conductor, etc.
    
    # Saldos Disponibles (Se pueden ajustar individualmente)
    vacation_days = db.Column(db.Integer, default=22) # Días laborables por defecto
    personal_days = db.Column(db.Integer, default=6)  # Asuntos propios (Moscosos)
    extra_hours = db.Column(db.Float, default=0.0)    # Horas acumuladas positivas
    
    # Historial de Notas (Para apuntar "pidió el día tal por WhatsApp")
    logs = db.relationship('Log', backref='worker', lazy=True)

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    action = db.Column(db.String(50)) # "Restar Vacaciones", "Sumar Horas", etc.
    amount = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(200))

# Crear tablas automáticamante al arrancar (Solo para prototipos simples)
with app.app_context():
    db.create_all()

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
    "vacaciones": {"dias": 22, "desc": "22 días laborables por año (o 30 naturales)."},
    "asuntos_propios": {"dias": 6, "desc": "6 días de libre disposición (Moscosos). No acumulables a vacaciones."},
    "matrimonio": {"dias": 15, "desc": "15 días naturales por matrimonio o registro pareja de hecho."},
    "nacimiento": {"dias": 3, "desc": "3 días (o 5 si hay desplazamiento)."},
    "fallecimiento_1": {"dias": 3, "desc": "Cónyuge o familiares 1º grado (Padres/Hijos). 5 si desplazamiento."},
    "fallecimiento_2": {"dias": 2, "desc": "Familiares 2º grado (Abuelos/Nietos/Hermanos). 4 si desplazamiento."},
    "mudanza": {"dias": 1, "desc": "1 día por traslado de domicilio habitual."},
    "deber_inexcusable": {"dias": 0, "desc": "Tiempo indispensable para el cumplimiento (Juicios, Voto, etc)."},
    "medico": {"dias": 0, "desc": "Tiempo indispensable para médico especialista (SS)."}
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
    new_worker = Worker(name=name, category=category)
    db.session.add(new_worker)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/init_db')
def init_db():
    db.drop_all() # ¡Importante! Borra lo viejo para meter los nuevos campos de Bajas
    db.create_all()
    # Datos de demostración
    if not Worker.query.first():
        w1 = Worker(name="Manuel Pérez", category="Peón Limpiador de Colegios")
        w2 = Worker(name="Antonio Obrero", category="Peón Limpieza Viaria")
        w3 = Worker(name="Luisa Conductora", category="Conductor Recogida")
        db.session.add_all([w1, w2, w3])
        db.session.commit()
        return "Base de datos REINICIADA con estructura de Bajas."
    return "La base de datos ya existe."

if __name__ == '__main__':
    app.run(debug=True, port=5001)
