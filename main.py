from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
import traceback
import textwrap
import time
import logging

# ================================================
# CONFIGURATION LOGGING
# ================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://hicham558.github.io", "http://localhost:*", "*"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-User-ID", "Authorization"],
    "supports_credentials": True,
    "max_age": 86400
}})

# ================================================
# MIDDLEWARE POUR PERFORMANCE
# ================================================
@app.before_request
def start_timer():
    """Démarre un timer pour chaque requête"""
    request.start_time = time.time()
    logger.info(f"▶️ {request.method} {request.path}")

@app.after_request
def log_request(response):
    """Log le temps de réponse"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        logger.info(f"✅ {request.method} {request.path} - {response.status_code} - {duration:.2f}s")
        
        # Warning si la requête prend trop de temps
        if duration > 20:
            logger.warning(f"⚠️ Requête lente: {duration:.2f}s pour {request.path}")
    
    return response

# ================================================
# CONFIGURATION BASE DE DONNÉES OPTIMISÉE
# ================================================
try:
    DATABASE_URL = os.environ['DATABASE_URL']
    logger.info("✅ DATABASE_URL chargée depuis environnement")
except KeyError:
    logger.info("🔧 DATABASE_URL absente - Mode développement local")
    DATABASE_URL = "postgresql://localhost/anapath"

def get_db():
    """Connexion PostgreSQL optimisée pour Render"""
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=5,           # Timeout de connexion court
            keepalives=1,                # Active keepalive
            keepalives_idle=30,          # 30s d'inactivité avant keepalive
            keepalives_interval=10,      # Envoie keepalive toutes les 10s
            keepalives_count=3           # 3 tentatives max
        )
        return conn
    except Exception as e:
        logger.error(f"❌ ERREUR CONNEXION DB: {str(e)}")
        raise

# ================================================
# DÉCORATEUR POUR GESTION AUTOMATIQUE DB
# ================================================
def with_db_connection(func):
    """Décorateur pour gérer automatiquement les connexions DB"""
    def wrapper(*args, **kwargs):
        conn = None
        cur = None
        try:
            conn = get_db()
            cur = conn.cursor()
            return func(conn, cur, *args, **kwargs)
        except Exception as e:
            logger.error(f"❌ Erreur dans {func.__name__}: {str(e)}")
            raise
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    wrapper.__name__ = func.__name__
    return wrapper

# ================================================
# INITIALISATION DE LA BASE DE DONNÉES
# ================================================
def init_db():
    """Initialisation optimisée des tables"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        logger.info("🔄 Initialisation des tables...")
        
        # Utilisateurs
        cur.execute('''
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                numero SERIAL,
                nom VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                statut VARCHAR(50) DEFAULT 'utilisateur',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, numero)
            )
        ''')
        
        # Patients
        cur.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                nom VARCHAR(255) NOT NULL,
                age INTEGER,
                sexe VARCHAR(1),
                telephone VARCHAR(50),
                adresse TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Médecins
        cur.execute('''
            CREATE TABLE IF NOT EXISTS medecins (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                nom VARCHAR(255) NOT NULL,
                specialite VARCHAR(255),
                service VARCHAR(255),
                telephone VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Comptes rendus
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comptes_rendus (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                numero_enregistrement VARCHAR(100) NOT NULL,
                date_compte_rendu DATE NOT NULL,
                medecin_id INTEGER REFERENCES medecins(id) ON DELETE SET NULL,
                utilisateur_id INTEGER REFERENCES utilisateurs(numero) ON DELETE SET NULL,
                service_hospitalier VARCHAR(255),
                patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
                nature_prelevement TEXT,
                date_prelevement DATE,
                renseignements_cliniques TEXT,
                macroscopie TEXT,
                microscopie TEXT,
                conclusion TEXT,
                statut VARCHAR(50) DEFAULT 'en_cours',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, numero_enregistrement)
            )
        ''')
        
        # Index pour améliorer les performances
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_comptes_rendus_user_id 
            ON comptes_rendus(user_id)
        ''')
        
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_patients_user_id 
            ON patients(user_id)
        ''')
        
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_medecins_user_id 
            ON medecins(user_id)
        ''')
        
        conn.commit()
        logger.info("✅ Tables initialisées avec succès")
        
    except Exception as e:
        logger.error(f"❌ ERREUR INIT DB: {str(e)}")
        traceback.print_exc()
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

# ================================================
# GESTION GLOBALE DES ERREURS
# ================================================
@app.errorhandler(Exception)
def handle_error(e):
    """Gestion centralisée des erreurs"""
    logger.error(f"❌ ERREUR: {str(e)}")
    traceback.print_exc()
    return jsonify({
        'erreur': str(e),
        'type': type(e).__name__
    }), 500

# ================================================
# ENDPOINTS DE SANTÉ (pour Render)
# ================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'ANAPATH API',
        'version': '1.0.0',
        'status': 'operational',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de santé simple pour Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/health/db', methods=['GET'])
def health_db():
    """Vérifie rapidement la connexion à la DB"""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1 as test')
        result = cur.fetchone()
        return jsonify({
            'database': 'connected',
            'test': result['test']
        })
    except Exception as e:
        return jsonify({
            'database': 'error',
            'message': str(e)
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/test-db', methods=['GET'])
def test_db():
    """Tester la connexion DB"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT version()')
        version = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({
            'status': 'success',
            'database': version
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ================================================
# UTILISATEURS (avec décorateur)
# ================================================
@app.route('/liste_utilisateurs', methods=['GET'])
@with_db_connection
def liste_utilisateurs(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        cur.execute(
            'SELECT numero, nom, statut FROM utilisateurs WHERE user_id = %s ORDER BY numero',
            (user_id,)
        )
        users = cur.fetchall()
        logger.info(f"📋 Liste utilisateurs: {len(users)} trouvés")
        return jsonify([dict(u) for u in users])
    
    except Exception as e:
        logger.error(f"❌ Erreur liste_utilisateurs: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/ajouter_utilisateur', methods=['POST'])
@with_db_connection
def ajouter_utilisateur(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    try:
        logger.info(f"➕ Ajout utilisateur: {data['nom']}")
        
        cur.execute("SELECT nextval('utilisateurs_id_seq') as next_id")
        next_id = cur.fetchone()['next_id']
        
        cur.execute('''
            INSERT INTO utilisateurs (id, user_id, numero, nom, password, statut)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, numero, nom, statut
        ''', (
            next_id,
            user_id,
            next_id,
            data['nom'],
            data['password2'],
            data.get('statut', 'utilisateur')
        ))
        
        new_user = cur.fetchone()
        conn.commit()
        
        logger.info(f"✅ Utilisateur créé: ID={new_user['id']}, Nom={new_user['nom']}")
        return jsonify(dict(new_user)), 201
    
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Erreur ajouter_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/valider_utilisateur', methods=['POST'])
@with_db_connection
def valider_utilisateur(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    try:
        cur.execute('''
            SELECT numero, nom, statut
            FROM utilisateurs
            WHERE user_id = %s AND nom = %s AND password = %s
        ''', (user_id, data['nom'], data['password2']))
        
        user = cur.fetchone()
        if not user:
            logger.warning(f"❌ Validation échouée pour: {data['nom']}")
            return jsonify({'erreur': 'Identifiants invalides'}), 401
        
        logger.info(f"✅ Utilisateur validé: {user['nom']}")
        return jsonify({'utilisateur': dict(user)})
    
    except Exception as e:
        logger.error(f"❌ Erreur valider_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# PATIENTS (avec décorateur)
# ================================================
@app.route('/patients', methods=['GET', 'POST'])
@with_db_connection
def patients(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'GET':
            cur.execute('''
                SELECT id, nom, age, sexe, telephone, adresse, created_at
                FROM patients
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 100  # Limite pour éviter les timeouts
            ''', (user_id,))
            patients_list = cur.fetchall()
            logger.info(f"📋 Liste patients: {len(patients_list)} trouvés")
            return jsonify([dict(p) for p in patients_list])
        
        elif request.method == 'POST':
            data = request.json
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                INSERT INTO patients (user_id, nom, age, sexe, telephone, adresse)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, nom, age, sexe, telephone, adresse
            ''', (
                user_id,
                data['nom'],
                data.get('age'),
                data.get('sexe'),
                data.get('telephone'),
                data.get('adresse')
            ))
            
            new_patient = cur.fetchone()
            conn.commit()
            
            logger.info(f"✅ Patient créé: {new_patient['nom']}")
            return jsonify(dict(new_patient)), 201
    
    except Exception as e:
        if request.method == 'POST':
            conn.rollback()
        logger.error(f"❌ Erreur patients: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/patients/<int:id>', methods=['PUT', 'DELETE'])
@with_db_connection
def patient_detail(conn, cur, id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'PUT':
            data = request.json
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                UPDATE patients
                SET nom = %s, age = %s, sexe = %s, telephone = %s, adresse = %s
                WHERE user_id = %s AND id = %s
            ''', (
                data['nom'],
                data.get('age'),
                data.get('sexe'),
                data.get('telephone'),
                data.get('adresse'),
                user_id,
                id
            ))
            conn.commit()
            
            logger.info(f"✏️ Patient modifié: ID={id}")
            return jsonify({'message': 'Patient modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM patients WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            
            logger.info(f"🗑️ Patient supprimé: ID={id}")
            return jsonify({'message': 'Patient supprimé'})
    
    except Exception as e:
        if request.method == 'PUT':
            conn.rollback()
        logger.error(f"❌ Erreur patient_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# MÉDECINS (avec décorateur)
# ================================================
@app.route('/medecins', methods=['GET', 'POST'])
@with_db_connection
def medecins(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'GET':
            cur.execute('''
                SELECT id, nom, specialite, service, telephone, created_at
                FROM medecins
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 100  # Limite pour éviter les timeouts
            ''', (user_id,))
            medecins_list = cur.fetchall()
            logger.info(f"📋 Liste médecins: {len(medecins_list)} trouvés")
            return jsonify([dict(m) for m in medecins_list])
        
        elif request.method == 'POST':
            data = request.json
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                INSERT INTO medecins (user_id, nom, specialite, service, telephone)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nom, specialite, service, telephone
            ''', (
                user_id,
                data['nom'],
                data.get('specialite'),
                data.get('service'),
                data.get('telephone')
            ))
            
            new_medecin = cur.fetchone()
            conn.commit()
            
            logger.info(f"✅ Médecin créé: {new_medecin['nom']}")
            return jsonify(dict(new_medecin)), 201
    
    except Exception as e:
        if request.method == 'POST':
            conn.rollback()
        logger.error(f"❌ Erreur medecins: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/medecins/<int:id>', methods=['PUT', 'DELETE'])
@with_db_connection
def medecin_detail(conn, cur, id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'PUT':
            data = request.json
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                UPDATE medecins
                SET nom = %s, specialite = %s, service = %s, telephone = %s
                WHERE user_id = %s AND id = %s
            ''', (
                data['nom'],
                data.get('specialite'),
                data.get('service'),
                data.get('telephone'),
                user_id,
                id
            ))
            conn.commit()
            
            logger.info(f"✏️ Médecin modifié: ID={id}")
            return jsonify({'message': 'Médecin modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM medecins WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            
            logger.info(f"🗑️ Médecin supprimé: ID={id}")
            return jsonify({'message': 'Médecin supprimé'})
    
    except Exception as e:
        if request.method == 'PUT':
            conn.rollback()
        logger.error(f"❌ Erreur medecin_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# COMPTES RENDUS (avec décorateur et optimisations)
# ================================================
@app.route('/comptes-rendus', methods=['GET', 'POST'])
@with_db_connection
def comptes_rendus(conn, cur):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'GET':
            # Version optimisée avec LIMIT pour éviter les timeouts
            cur.execute('''
                SELECT cr.id, cr.numero_enregistrement, cr.date_compte_rendu,
                       cr.statut, cr.date_prelevement, cr.created_at,
                       p.nom as patient_nom, m.nom as medecin_nom,
                       u.nom as utilisateur_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero AND cr.user_id = u.user_id
                WHERE cr.user_id = %s
                ORDER BY cr.created_at DESC
                LIMIT 50  # Limite importante pour éviter les timeouts
            ''', (user_id,))
            
            reports = cur.fetchall()
            logger.info(f"📋 Liste comptes rendus: {len(reports)} trouvés")
            return jsonify([dict(r) for r in reports])
        
        elif request.method == 'POST':
            data = request.json
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 
                       'patient_id', 'nature_prelevement', 'date_prelevement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            utilisateur_id = data.get('utilisateur_id')
            
            logger.info(f"➕ Création compte rendu: {data['numero_enregistrement']}")
            
            cur.execute('''
                INSERT INTO comptes_rendus (
                    user_id, utilisateur_id, numero_enregistrement, date_compte_rendu,
                    medecin_id, service_hospitalier, patient_id,
                    nature_prelevement, date_prelevement, renseignements_cliniques,
                    macroscopie, microscopie, conclusion, statut
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                utilisateur_id,
                data['numero_enregistrement'],
                data['date_compte_rendu'],
                data['medecin_id'],
                data.get('service_hospitalier'),
                data['patient_id'],
                data['nature_prelevement'],
                data['date_prelevement'],
                data.get('renseignements_cliniques'),
                data.get('macroscopie'),
                data.get('microscopie'),
                data.get('conclusion'),
                data.get('statut', 'en_cours')
            ))
            
            new_report = cur.fetchone()
            conn.commit()
            
            logger.info(f"✅ Compte rendu créé: ID={new_report['id']}")
            return jsonify(dict(new_report)), 201
    
    except Exception as e:
        if request.method == 'POST':
            conn.rollback()
        logger.error(f"❌ Erreur comptes_rendus: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/comptes-rendus/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@with_db_connection
def compte_rendu_detail(conn, cur, id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        if request.method == 'GET':
            cur.execute('''
                SELECT cr.*,
                       p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                       m.nom as medecin_nom,
                       u.nom as utilisateur_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero AND cr.user_id = u.user_id
                WHERE cr.user_id = %s AND cr.id = %s
            ''', (user_id, id))
            
            report = cur.fetchone()
            if not report:
                logger.warning(f"❌ Compte rendu non trouvé: ID={id}")
                return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
            
            logger.info(f"📄 Détails compte rendu: ID={id}")
            return jsonify(dict(report))
        
        elif request.method == 'PUT':
            data = request.json
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id',
                       'patient_id', 'nature_prelevement', 'date_prelevement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            logger.info(f"✏️ Modification compte rendu: ID={id}")
            
            cur.execute('''
                UPDATE comptes_rendus SET
                    utilisateur_id = %s,
                    numero_enregistrement = %s, date_compte_rendu = %s,
                    medecin_id = %s, service_hospitalier = %s, patient_id = %s,
                    nature_prelevement = %s, date_prelevement = %s,
                    renseignements_cliniques = %s,
                    macroscopie = %s, microscopie = %s, conclusion = %s,
                    statut = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND id = %s
            ''', (
                data.get('utilisateur_id'),
                data['numero_enregistrement'],
                data['date_compte_rendu'],
                data['medecin_id'],
                data.get('service_hospitalier'),
                data['patient_id'],
                data['nature_prelevement'],
                data['date_prelevement'],
                data.get('renseignements_cliniques'),
                data.get('macroscopie'),
                data.get('microscopie'),
                data.get('conclusion'),
                data.get('statut'),
                user_id,
                id
            ))
            conn.commit()
            
            logger.info(f"✅ Compte rendu modifié: ID={id}")
            return jsonify({'message': 'Compte rendu modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM comptes_rendus WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            
            logger.info(f"🗑️ Compte rendu supprimé: ID={id}")
            return jsonify({'message': 'Compte rendu supprimé'})
    
    except Exception as e:
        if request.method in ['PUT', 'POST']:
            conn.rollback()
        logger.error(f"❌ Erreur compte_rendu_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
    user_id = request.headers.get('X-User-ID') or request.args.get('user_id')
    
    logger.info(f"🖨️ Demande impression CR ID: {id}, user_id: {user_id}")
    
    if not user_id:
        logger.error("❌ X-User-ID manquant pour impression")
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT cr.*,
                   p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                   m.nom as medecin_nom,
                   u.nom as utilisateur_nom
            FROM comptes_rendus cr
            LEFT JOIN patients p ON cr.patient_id = p.id
            LEFT JOIN medecins m ON cr.medecin_id = m.id
            LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero AND cr.user_id = u.user_id
            WHERE cr.user_id = %s AND cr.id = %s
        ''', (user_id, id))
        
        report = cur.fetchone()
        
        if not report:
            logger.error(f"❌ Compte rendu {id} non trouvé pour impression")
            return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
        
        logger.info(f"📄 Génération PDF pour CR {id}")
        
        # Génération PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # En-tête
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, "ANAPATH ELYOUSR")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, "Laboratoire d'Anatomie & Cytologie Pathologiques")
        p.drawString(50, height - 85, "Dr. BENFOULA Amel épouse ERROUANE")
        
        # Titre principal
        y = height - 120
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "COMPTE RENDU CYTO-PATHOLOGIQUE")
        
        # Infos principales
        y -= 30
        p.setFont("Helvetica", 10)
        p.drawString(50, y, f"N° Enregistrement : {report['numero_enregistrement']}")
        y -= 15
        p.drawString(50, y, f"Date du compte rendu : {report['date_compte_rendu']}")
        
        # Utilisateur qui a créé le CR
        if report.get('utilisateur_nom'):
            y -= 15
            p.drawString(50, y, f"Créé par : {report['utilisateur_nom']}")
        
        y -= 30
        p.drawString(50, y, f"Patient : {report['patient_nom'] or 'Non renseigné'}")
        y -= 15
        p.drawString(50, y, f"Âge : {report['patient_age'] or '-'} | Sexe : {report['patient_sexe'] or '-'}")
        
        y -= 15
        p.drawString(50, y, f"Médecin demandeur : {report['medecin_nom'] or 'Non renseigné'}")
        
        y -= 15
        p.drawString(50, y, f"Service/Hôpital : {report.get('service_hospitalier', '-')}")
        
        y -= 30
        p.drawString(50, y, f"Date du prélèvement : {report['date_prelevement'] or '-'}")
        y -= 15
        p.drawString(50, y, f"Nature/Siège du prélèvement : {report['nature_prelevement'] or 'Non renseigné'}")
        
        # Sections du rapport
        def add_section(title, content):
            nonlocal y
            y -= 30
            if y < 100:
                p.showPage()
                y = height - 50
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y, title)
            y -= 20
            p.setFont("Helvetica", 10)
            for line in textwrap.wrap(content or 'Non renseigné', width=90):
                if y < 100:
                    p.showPage()
                    y = height - 50
                p.drawString(60, y, line)
                y -= 15
        
        add_section("Renseignements Cliniques Fournis :", report.get('renseignements_cliniques', ''))
        add_section("MACROSCOPIE :", report.get('macroscopie', ''))
        add_section("MICROSCOPIE :", report.get('microscopie', ''))
        add_section("CONCLUSION :", report.get('conclusion', ''))
        
        p.save()
        buffer.seek(0)
        
        logger.info(f"✅ PDF généré avec succès pour CR {id}")
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"CR_{report['numero_enregistrement'] or id}.pdf",
            mimetype='application/pdf'
        )
    
    except Exception as e:
        logger.error(f"❌ Erreur impression: {str(e)}")
        return jsonify({'erreur': f'Erreur serveur: {str(e)}'}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ================================================
# DÉMARRAGE
# ================================================
if __name__ == '__main__':
    logger.info("🚀 Démarrage ANAPATH API...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ Avertissement init_db: {str(e)}")
    
    # Mode production pour Render
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
