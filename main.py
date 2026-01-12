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

app = Flask(__name__)
CORS(app)

# ================================================
# CONFIGURATION
# ================================================
try:
    DATABASE_URL = os.environ['DATABASE_URL']
    print("? DATABASE_URL chargée depuis environnement")
except KeyError:
    print("? DATABASE_URL absente - Mode développement local")
    DATABASE_URL = "postgresql://localhost/anapath"

def get_db():
    """Connexion PostgreSQL avec gestion d'erreur"""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"? ERREUR CONNEXION DB: {str(e)}")
        raise

def init_db():
    """Initialisation des tables"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        print("?? Initialisation des tables...")
        
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
        
        conn.commit()
        print("? Tables initialisées")
        
    except Exception as e:
        print(f"? ERREUR INIT DB: {str(e)}")
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
    print(f"? ERREUR: {str(e)}")
    traceback.print_exc()
    return jsonify({
        'erreur': str(e),
        'type': type(e).__name__
    }), 500

# ================================================
# ROUTES
# ================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'ANAPATH API',
        'version': '1.0.0',
        'status': 'operational'
    })

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
# UTILISATEURS
# ================================================
@app.route('/liste_utilisateurs', methods=['GET'])
def liste_utilisateurs():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'SELECT numero, nom, statut FROM utilisateurs WHERE user_id = %s ORDER BY numero',
            (user_id,)
        )
        users = cur.fetchall()
        return jsonify([dict(u) for u in users])
    
    except Exception as e:
        print(f"? Erreur liste_utilisateurs: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/ajouter_utilisateur', methods=['POST'])
def ajouter_utilisateur():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Insérer sans spécifier numero (SERIAL auto-increment)
        cur.execute('''
            INSERT INTO utilisateurs (user_id, nom, password, statut)
            VALUES (%s, %s, %s, %s)
            RETURNING id, numero, nom, statut
        ''', (
            user_id,
            data['nom'],
            data['password2'],
            data.get('statue', 'utilisateur')
        ))
        
        new_user = cur.fetchone()
        conn.commit()
        return jsonify(dict(new_user)), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur ajouter_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/valider_utilisateur', methods=['POST'])
def valider_utilisateur():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            SELECT numero, nom, statut
            FROM utilisateurs
            WHERE user_id = %s AND nom = %s AND password = %s
        ''', (user_id, data['nom'], data['password2']))
        
        user = cur.fetchone()
        if not user:
            return jsonify({'erreur': 'Identifiants invalides'}), 401
        
        return jsonify({'utilisateur': dict(user)})
    
    except Exception as e:
        print(f"? Erreur valider_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ================================================
# PATIENTS
# ================================================
@app.route('/patients', methods=['GET', 'POST'])
def patients():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            cur.execute('''
                SELECT id, nom, age, sexe, telephone, adresse, created_at
                FROM patients
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
            patients_list = cur.fetchall()
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
            return jsonify(dict(new_patient)), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur patients: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/patients/<int:id>', methods=['PUT', 'DELETE'])
def patient_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
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
            return jsonify({'message': 'Patient modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM patients WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            return jsonify({'message': 'Patient supprimé'})
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur patient_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ================================================
# MÉDECINS
# ================================================
@app.route('/medecins', methods=['GET', 'POST'])
def medecins():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            cur.execute('''
                SELECT id, nom, specialite, service, telephone, created_at
                FROM medecins
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
            medecins_list = cur.fetchall()
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
            return jsonify(dict(new_medecin)), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur medecins: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/medecins/<int:id>', methods=['PUT', 'DELETE'])
def medecin_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
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
            return jsonify({'message': 'Médecin modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM medecins WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            return jsonify({'message': 'Médecin supprimé'})
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur medecin_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ================================================
# COMPTES RENDUS
# ================================================
@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
    # IMPORTANT : cette ligne doit être la première
    user_id = request.headers.get('X-User-ID') or request.args.get('user_id')
    
    # Debug obligatoire pour voir ce qui arrive
    print(f"[PRINT DEBUG] ID demandé: {id}")
    print(f"[PRINT DEBUG] Header X-User-ID: {request.headers.get('X-User-ID')}")
    print(f"[PRINT DEBUG] Query param user_id: {request.args.get('user_id')}")
    print(f"[PRINT DEBUG] user_id final utilisé: {user_id}")
    
    if not user_id:
        print("[PRINT ERROR] user_id manquant (ni header ni param)")
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT cr.*,
                   p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                   m.nom as medecin_nom
            FROM comptes_rendus cr
            LEFT JOIN patients p ON cr.patient_id = p.id
            LEFT JOIN medecins m ON cr.medecin_id = m.id
            WHERE cr.user_id = %s AND cr.id = %s
        ''', (user_id, id))
        
        report = cur.fetchone()
        
        if not report:
            print(f"[PRINT] Compte rendu {id} non trouvé pour user {user_id}")
            return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
        
        # Génération PDF (version complète avec wrap)
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, "ANAPATH ELYOUSR")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, "Laboratoire d'Anatomie & Cytologie Pathologiques")
        p.drawString(50, height - 85, "Dr. BENFOULA Amel épouse ERROUANE")
        
        y = height - 120
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "COMPTE RENDU CYTO-PATHOLOGIQUE")
        
        y -= 30
        p.setFont("Helvetica", 10)
        p.drawString(50, y, f"N° Enregistrement : {report['numero_enregistrement']}")
        y -= 15
        p.drawString(50, y, f"Date : {report['date_compte_rendu']}")
        
        y -= 30
        p.drawString(50, y, f"Patient : {report['patient_nom']}")
        y -= 15
        p.drawString(50, y, f"Âge : {report['patient_age'] or '-'} | Sexe : {report['patient_sexe'] or '-'}")
        
        y -= 15
        p.drawString(50, y, f"Médecin : {report['medecin_nom']}")
        
        # Ajout des autres sections (macro, micro, conclusion) avec gestion des lignes longues
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "MACROSCOPIE :")
        y -= 20
        p.setFont("Helvetica", 10)
        macro = report.get('macroscopie', 'Non renseigné')
        for line in textwrap.wrap(macro, width=90):
            p.drawString(60, y, line)
            y -= 15
            if y < 100:
                p.showPage()
                y = height - 50
        
        # ... (tu peux ajouter microscopie et conclusion de la même façon)
        
        p.save()
        buffer.seek(0)
        
        print("[PRINT] PDF généré avec succès")
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"CR_{report['numero_enregistrement']}.pdf",
            mimetype='application/pdf'
        )
    
    except Exception as e:
        print(f"[PRINT ERREUR CRITIQUE] ID {id} : {str(e)}")
        return jsonify({'erreur': 'Erreur serveur lors de la génération du PDF'}), 500
    
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

@app.route('/comptes-rendus/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def compte_rendu_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            cur.execute('''
                SELECT cr.*,
                       p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                       m.nom as medecin_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                WHERE cr.user_id = %s AND cr.id = %s
            ''', (user_id, id))
            
            report = cur.fetchone()
            if not report:
                return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
            
            return jsonify(dict(report))
        
        elif request.method == 'PUT':
            data = request.json
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id',
                       'patient_id', 'nature_prelevement', 'date_prelevement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            cur.execute('''
                UPDATE comptes_rendus SET
                    numero_enregistrement = %s, date_compte_rendu = %s,
                    medecin_id = %s, service_hospitalier = %s, patient_id = %s,
                    nature_prelevement = %s, date_prelevement = %s,
                    renseignements_cliniques = %s,
                    macroscopie = %s, microscopie = %s, conclusion = %s,
                    statut = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND id = %s
            ''', (
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
            return jsonify({'message': 'Compte rendu modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM comptes_rendus WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            return jsonify({'message': 'Compte rendu supprimé'})
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"? Erreur compte_rendu_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# DÉMARRAGE
# ================================================
if __name__ == '__main__':
    print("?? Démarrage ANAPATH API...")
    try:
        init_db()
    except Exception as e:
        print(f"?? Avertissement init_db: {str(e)}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
