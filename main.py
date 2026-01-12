from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

app = Flask(__name__)
CORS(app)

# ================================================
# CONFIGURATION DATABASE (strict, obligatoire sur Render)
# ================================================
try:
    DATABASE_URL = os.environ['DATABASE_URL']
    print("DATABASE_URL chargée depuis les variables d'environnement Render")
except KeyError:
    print("ERREUR FATALE : DATABASE_URL ABSENTE dans les variables d'environnement !")
    raise ValueError("DATABASE_URL manquante → impossible de démarrer l'application")

def get_db():
    """Connexion PostgreSQL avec logs"""
    try:
        print("Tentative de connexion PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        print("Connexion PostgreSQL réussie !")
        return conn
    except Exception as e:
        print(f"ERREUR CRITIQUE CONNEXION DB : {str(e)}")
        print(f"URL utilisée (cachée) : {DATABASE_URL.split('@')[0]}...")
        raise

def init_db():
    """Initialisation des tables (à appeler une seule fois)"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        print("Initialisation tables en cours...")
        
        # Table utilisateurs
        cur.execute('''
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                numero INTEGER UNIQUE,
                nom VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                statut VARCHAR(50) DEFAULT 'utilisateur',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table patients
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
        
        # Table médecins
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
        
        # Table comptes rendus
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comptes_rendus (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                numero_enregistrement VARCHAR(100) UNIQUE NOT NULL,
                date_compte_rendu DATE NOT NULL,
                medecin_id INTEGER REFERENCES medecins(id),
                service_hospitalier VARCHAR(255),
                patient_id INTEGER REFERENCES patients(id),
                nature_prelevement TEXT,
                date_prelevement DATE,
                renseignements_cliniques TEXT,
                macroscopie TEXT,
                microscopie TEXT,
                conclusion TEXT,
                statut VARCHAR(50) DEFAULT 'en_cours',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        print("Tables initialisées (ou déjà existantes)")
    except Exception as e:
        print(f"ERREUR INIT DB : {str(e)}")
        raise
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

# ================================================
# ROUTES UTILISATEURS
# ================================================
@app.route('/liste_utilisateurs', methods=['GET'])
def liste_utilisateurs():
    print("Requête : /liste_utilisateurs")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT numero, nom, statut FROM utilisateurs WHERE user_id = %s', (user_id,))
        users = cur.fetchall()
        print(f"Utilisateurs trouvés : {len(users)}")
        return jsonify([dict(u) for u in users])
    except Exception as e:
        print(f"ERREUR /liste_utilisateurs : {str(e)}")
        return jsonify({'erreur': 'Erreur interne serveur'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/ajouter_utilisateur', methods=['POST'])
def ajouter_utilisateur():
    print("Requête : /ajouter_utilisateur")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    data = request.json
    if not data or 'nom' not in data:
        return jsonify({'erreur': 'Données invalides (nom obligatoire)'}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT MAX(numero) FROM utilisateurs WHERE user_id = %s', (user_id,))
        result = cur.fetchone()
        next_num = (result['max'] or 0) + 1
        
        cur.execute('''
            INSERT INTO utilisateurs (user_id, numero, nom, password, statut)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, numero, nom, statut
        ''', (user_id, next_num, data['nom'], data['password2'], data.get('statue', 'utilisateur')))
        
        new_user = cur.fetchone()
        conn.commit()
        print(f"Utilisateur ajouté : {new_user['nom']}")
        return jsonify(dict(new_user))
    except Exception as e:
        print(f"ERREUR /ajouter_utilisateur : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur interne serveur'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/valider_utilisateur', methods=['POST'])
def valider_utilisateur():
    print("Requête : /valider_utilisateur")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Données invalides'}), 400
    
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
            print("Identifiants invalides")
            return jsonify({'erreur': 'Identifiants invalides'}), 401
        
        print("Utilisateur validé")
        return jsonify({'utilisateur': dict(user)})
    except Exception as e:
        print(f"ERREUR /valider_utilisateur : {str(e)}")
        return jsonify({'erreur': 'Erreur interne serveur'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/modifier_utilisateur/<int:numero>', methods=['PUT'])
def modifier_utilisateur(numero):
    print(f"Requête : /modifier_utilisateur/{numero}")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    data = request.json
    if not data or 'nom' not in data:
        return jsonify({'erreur': 'Nom obligatoire'}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if 'password2' in data and data['password2']:
            cur.execute('''
                UPDATE utilisateurs
                SET nom = %s, password = %s, statut = %s
                WHERE user_id = %s AND numero = %s
            ''', (data['nom'], data['password2'], data.get('statue', 'utilisateur'), user_id, numero))
        else:
            cur.execute('''
                UPDATE utilisateurs
                SET nom = %s, statut = %s
                WHERE user_id = %s AND numero = %s
            ''', (data['nom'], data.get('statue', 'utilisateur'), user_id, numero))
        
        conn.commit()
        print(f"Utilisateur {numero} modifié")
        return jsonify({'message': 'Utilisateur modifié'})
    except Exception as e:
        print(f"ERREUR /modifier_utilisateur : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur interne serveur'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/supprimer_utilisateur/<int:numero>', methods=['DELETE'])
def supprimer_utilisateur(numero):
    print(f"Requête : /supprimer_utilisateur/{numero}")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM utilisateurs WHERE user_id = %s AND numero = %s', (user_id, numero))
        conn.commit()
        print(f"Utilisateur {numero} supprimé")
        return jsonify({'message': 'Utilisateur supprimé'})
    except Exception as e:
        print(f"ERREUR /supprimer_utilisateur : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur interne serveur'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

# ================================================
# PATIENTS
# ================================================
@app.route('/patients', methods=['GET', 'POST'])
def patients():
    print("Requête : /patients")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            print(f"GET patients pour user_id = {user_id}")
            cur.execute('''
                SELECT id, nom, age, sexe, telephone, adresse, created_at
                FROM patients
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
            patients_list = cur.fetchall()
            print(f"Patients trouvés : {len(patients_list)}")
            return jsonify([dict(p) for p in patients_list])
        
        elif request.method == 'POST':
            data = request.json
            print("POST patient - données:", data)
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                INSERT INTO patients (user_id, nom, age, sexe, telephone, adresse)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, nom, age, sexe, telephone, adresse
            ''', (user_id, data['nom'], data.get('age'), data.get('sexe'),
                  data.get('telephone'), data.get('adresse')))
            
            new_patient = cur.fetchone()
            conn.commit()
            print(f"Patient créé - ID: {new_patient['id']}")
            return jsonify(dict(new_patient)), 201
    except Exception as e:
        print(f"ERREUR /patients : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/patients/<int:id>', methods=['PUT', 'DELETE'])
def patient_detail(id):
    print(f"Requête : /patients/{id}")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'PUT':
            data = request.json
            print("PUT patient - données:", data)
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                UPDATE patients
                SET nom = %s, age = %s, sexe = %s, telephone = %s, adresse = %s
                WHERE user_id = %s AND id = %s
            ''', (data['nom'], data.get('age'), data.get('sexe'),
                  data.get('telephone'), data.get('adresse'), user_id, id))
            conn.commit()
            print(f"Patient {id} modifié")
            return jsonify({'message': 'Patient modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM patients WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            print(f"Patient {id} supprimé")
            return jsonify({'message': 'Patient supprimé'})
    except Exception as e:
        print(f"ERREUR /patients/{id} : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

# ================================================
# MÉDECINS
# ================================================
@app.route('/medecins', methods=['GET', 'POST'])
def medecins():
    print("Requête : /medecins")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            print(f"GET medecins pour user_id = {user_id}")
            cur.execute('''
                SELECT id, nom, specialite, service, telephone, created_at
                FROM medecins
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
            medecins_list = cur.fetchall()
            print(f"Médecins trouvés : {len(medecins_list)}")
            return jsonify([dict(m) for m in medecins_list])
        
        elif request.method == 'POST':
            data = request.json
            print("POST medecin - données:", data)
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                INSERT INTO medecins (user_id, nom, specialite, service, telephone)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nom, specialite, service, telephone
            ''', (user_id, data['nom'], data.get('specialite'),
                  data.get('service'), data.get('telephone')))
            
            new_medecin = cur.fetchone()
            conn.commit()
            print(f"Médecin créé - ID: {new_medecin['id']}")
            return jsonify(dict(new_medecin)), 201
    except Exception as e:
        print(f"ERREUR /medecins : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/medecins/<int:id>', methods=['PUT', 'DELETE'])
def medecin_detail(id):
    print(f"Requête : /medecins/{id}")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'PUT':
            data = request.json
            print("PUT medecin - données:", data)
            if not data or 'nom' not in data:
                return jsonify({'erreur': 'Nom obligatoire'}), 400
            
            cur.execute('''
                UPDATE medecins
                SET nom = %s, specialite = %s, service = %s, telephone = %s
                WHERE user_id = %s AND id = %s
            ''', (data['nom'], data.get('specialite'), data.get('service'),
                  data.get('telephone'), user_id, id))
            conn.commit()
            print(f"Médecin {id} modifié")
            return jsonify({'message': 'Médecin modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM medecins WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            print(f"Médecin {id} supprimé")
            return jsonify({'message': 'Médecin supprimé'})
    except Exception as e:
        print(f"ERREUR /medecins/{id} : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

# ================================================
# COMPTES RENDUS
# ================================================
@app.route('/comptes-rendus', methods=['GET', 'POST'])
def comptes_rendus():
    print("Requête : /comptes-rendus")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            print(f"GET comptes-rendus pour user_id = {user_id}")
            cur.execute('''
                SELECT cr.*,
                       p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                       m.nom as medecin_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                WHERE cr.user_id = %s
                ORDER BY cr.created_at DESC
            ''', (user_id,))
            reports = cur.fetchall()
            print(f"Comptes-rendus trouvés : {len(reports)}")
            return jsonify([dict(r) for r in reports])
        
        elif request.method == 'POST':
            data = request.json
            print("POST compte-rendu - données:", data)
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 'patient_id', 'nature_prelevement', 'date_prelevement']
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            cur.execute('''
                INSERT INTO comptes_rendus (
                    user_id, numero_enregistrement, date_compte_rendu,
                    medecin_id, service_hospitalier, patient_id,
                    nature_prelevement, date_prelevement, renseignements_cliniques,
                    macroscopie, microscopie, conclusion, statut
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id, data['numero_enregistrement'], data['date_compte_rendu'],
                data['medecin_id'], data.get('service_hospitalier'), data['patient_id'],
                data['nature_prelevement'], data['date_prelevement'],
                data.get('renseignements_cliniques'),
                data.get('macroscopie'), data.get('microscopie'),
                data.get('conclusion'), data.get('statut', 'en_cours')
            ))
            
            new_report = cur.fetchone()
            conn.commit()
            print(f"Compte-rendu créé - ID: {new_report['id']}")
            return jsonify(dict(new_report)), 201
    except Exception as e:
        print(f"ERREUR /comptes-rendus : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/comptes-rendus/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def compte_rendu_detail(id):
    print(f"Requête : /comptes-rendus/{id}")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
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
                print(f"Compte rendu {id} non trouvé")
                return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
            
            print(f"Compte rendu {id} chargé")
            return jsonify(dict(report))
        
        elif request.method == 'PUT':
            data = request.json
            print("PUT compte-rendu - données:", data)
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 'patient_id', 'nature_prelevement', 'date_prelevement']
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
                data['numero_enregistrement'], data['date_compte_rendu'],
                data['medecin_id'], data.get('service_hospitalier'), data['patient_id'],
                data['nature_prelevement'], data['date_prelevement'],
                data.get('renseignements_cliniques'),
                data.get('macroscopie'), data.get('microscopie'),
                data.get('conclusion'), data.get('statut'), user_id, id
            ))
            conn.commit()
            print(f"Compte rendu {id} modifié")
            return jsonify({'message': 'Compte rendu modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM comptes_rendus WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            print(f"Compte rendu {id} supprimé")
            return jsonify({'message': 'Compte rendu supprimé'})
    except Exception as e:
        print(f"ERREUR /comptes-rendus/{id} : {str(e)}")
        conn.rollback() if 'conn' in locals() else None
        return jsonify({'erreur': 'Erreur serveur interne'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
    print(f"Requête : /comptes-rendus/{id}/print")
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        print("401 : X-User-ID manquant")
        return jsonify({'erreur': 'Non autorisé'}), 401
    
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
            print(f"Compte rendu {id} non trouvé")
            return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
        
        print(f"Génération PDF pour compte rendu {id}")
        
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, "ANAPATH ELYOUSR")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, "Laboratoire d'Anatomie & Cytologie Pathologiques")
        p.drawString(50, height - 85, "Dr. BENFOULA Amel épouse ERROUANE")
        
        y = height - 120
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "COMPTE RENDU CYTO-PATHOLOGIQUE")
        
        y -= 30
        p.setFont("Helvetica", 10)
        p.drawString(50, y, f"N° Enregistrement: {report['numero_enregistrement']}")
        y -= 15
        p.drawString(50, y, f"Date: {report['date_compte_rendu']}")
        
        y -= 30
        p.drawString(50, y, f"Patient: {report['patient_nom']}")
        y -= 15
        p.drawString(50, y, f"Âge: {report['patient_age'] or '-'} | Sexe: {report['patient_sexe'] or '-'}")
        
        y -= 15
        p.drawString(50, y, f"Médecin: {report['medecin_nom']}")
        
        p.save()
        buffer.seek(0)
        
        return send_file(buffer, as_attachment=True,
                         download_name=f"CR_{report['numero_enregistrement']}.pdf",
                         mimetype='application/pdf')
    except Exception as e:
        print(f"ERREUR /print : {str(e)}")
        return jsonify({'erreur': 'Erreur génération PDF'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

# ================================================
# ROUTE RACINE
# ================================================
@app.route('/', methods=['GET'])
def home():
    print("Requête racine : /")
    return "API ANAPATH - Backend fonctionnel"

# ================================================
# DÉMARRAGE LOCAL (dev seulement)
# ================================================
if __name__ == '__main__':
    print("Mode développement local - démarrage...")
    try:
        init_db()
    except Exception as e:
        print("Échec init_db en local :", str(e))
    app.run(debug=True, host='0.0.0.0', port=5000)
