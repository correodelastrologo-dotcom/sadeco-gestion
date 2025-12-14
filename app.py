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

# --- RUTAS ---
@app.route('/')
def index():
    search = request.args.get('search', '')
    if search:
        workers = Worker.query.filter(Worker.name.contains(search)).all()
    else:
        workers = Worker.query.all()
    return render_template('index.html', workers=workers, categories=CATEGORIES)

@app.route('/worker/<int:id>')
def worker_detail(id):
    worker = Worker.query.get_or_404(id)
    return render_template('worker_detail.html', worker=worker)

@app.route('/update/<int:id>', methods=['POST'])
def update_worker(id):
    worker = Worker.query.get_or_404(id)
    type_action = request.form.get('type') # 'vacation', 'personal', 'hours'
    operation = request.form.get('operation') # 'add', 'subtract'
    amount = float(request.form.get('amount', 1))
    note = request.form.get('note', '')

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

    # Guardar Log
    new_log = Log(worker_id=worker.id, action=action_text, amount=amount, notes=note)
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
    db.create_all()
    # Datos de demostración
    if not Worker.query.first():
        w1 = Worker(name="Manuel Pérez", category="Peón Limpiador de Colegios")
        w2 = Worker(name="Antonio Obrero", category="Peón Limpieza Viaria")
        w3 = Worker(name="Luisa Conductora", category="Conductor Recogida")
        db.session.add_all([w1, w2, w3])
        db.session.commit()
        return "Base de datos creada con trabajadores de prueba."
    return "La base de datos ya existe."

if __name__ == '__main__':
    app.run(debug=True, port=5001)
