from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
from io import BytesIO
import traceback
import textwrap



app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://hicham558.github.io", "http://localhost:*", "*"],  # ton domaine GH Pages + localhost
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-User-ID", "Authorization"],
    "supports_credentials": True,
    "max_age": 86400  # cache preflight 24h
}})

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
# Fonction pour formater les dates
def format_date(date_str):
    if not date_str:
        return "-"
    try:
        date_obj = datetime.strptime(str(date_str), '%Y-%m-%d')
        return date_obj.strftime('%d/%m/%Y')
    except:
        return str(date_str)

# Fonction pour formater le sexe
def format_sexe(sexe_code):
    if sexe_code == 'M':
        return 'Masculin'
    elif sexe_code == 'F':
        return 'Féminin'
    else:
        return '-'
        
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
        
        # Version optimisée : utiliser nextval pour obtenir l'ID d'avance
        # D'abord obtenir le prochain ID de la séquence
        cur.execute("SELECT nextval('utilisateurs_id_seq') as next_id")
        next_id = cur.fetchone()['next_id']
        
        # Insérer avec id ET numero définis explicitement
        cur.execute('''
            INSERT INTO utilisateurs (id, user_id, numero, nom, password, statut)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, numero, nom, statut
        ''', (
            next_id,           # id (explicitement défini)
            user_id,
            next_id,           # numero = id
            data['nom'],
            data['password2'],
            data.get('statut', 'utilisateur')
        ))
        
        new_user = cur.fetchone()
        conn.commit()
        return jsonify(dict(new_user)), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur ajouter_utilisateur: {str(e)}")
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
# MODIFIER UN UTILISATEUR
# ================================================
@app.route('/utilisateurs/<int:numero>', methods=['PUT'])
def modifier_utilisateur(numero):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401

    data = request.json
    if not data:
        return jsonify({'erreur': 'Données manquantes'}), 400

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # Champs modifiables
        champs = []
        valeurs = []

        if 'nom' in data:
            champs.append("nom = %s")
            valeurs.append(data['nom'])
        if 'password2' in data and data['password2']:  # on ne change le mdp que s'il est fourni
            champs.append("password = %s")
            valeurs.append(data['password2'])
        if 'statut' in data:
            champs.append("statut = %s")
            valeurs.append(data['statut'])

        if not champs:
            return jsonify({'erreur': 'Aucun champ à modifier'}), 400

        valeurs.append(user_id)
        valeurs.append(numero)

        query = f"""
            UPDATE utilisateurs
            SET {', '.join(champs)}
            WHERE user_id = %s AND numero = %s
            RETURNING numero, nom, statut
        """

        cur.execute(query, valeurs)
        updated = cur.fetchone()

        if not updated:
            conn.rollback()
            return jsonify({'erreur': 'Utilisateur non trouvé ou non autorisé'}), 404

        conn.commit()
        return jsonify(dict(updated))

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur modification utilisateur {numero}: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# SUPPRIMER UN UTILISATEUR
# ================================================
@app.route('/utilisateurs/<int:numero>', methods=['DELETE'])
def supprimer_utilisateur(numero):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # On vérifie d'abord que l'utilisateur existe et appartient bien au user_id
        cur.execute(
            "SELECT numero FROM utilisateurs WHERE user_id = %s AND numero = %s",
            (user_id, numero)
        )
        if not cur.fetchone():
            return jsonify({'erreur': 'Utilisateur non trouvé ou non autorisé'}), 404

        # Suppression
        cur.execute(
            "DELETE FROM utilisateurs WHERE user_id = %s AND numero = %s",
            (user_id, numero)
        )

        conn.commit()
        return jsonify({'message': f'Utilisateur #{numero} supprimé'})

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur suppression utilisateur {numero}: {str(e)}")
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
                SELECT id, nom, age, sexe, telephone, adresse, solde, created_at
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
                INSERT INTO patients (user_id, nom, age, sexe, telephone, adresse, solde)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, nom, age, sexe, telephone, adresse, solde, created_at
            ''', (
                user_id,
                data['nom'],
                data.get('age'),
                data.get('sexe'),
                data.get('telephone'),
                data.get('adresse'),
                data.get('solde', 0)  # Valeur par défaut à 0 si non fourni
            ))

            new_patient = cur.fetchone()
            conn.commit()
            return jsonify(dict(new_patient)), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur patients: {str(e)}")
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

@app.route('/comptes-rendus', methods=['GET', 'POST'])
def comptes_rendus():
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
                       m.nom as medecin_nom,
                       u.nom as utilisateur_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero AND cr.user_id = u.user_id
                WHERE cr.user_id = %s
                ORDER BY cr.created_at DESC
            ''', (user_id,))
            reports = cur.fetchall()
            return jsonify([dict(r) for r in reports])
        
        elif request.method == 'POST':
            data = request.json
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 
                       'patient_id', 'nature_prelevement', 'date_prelevement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            # Récupérer utilisateur_id depuis les données ou depuis le header
            utilisateur_id = data.get('utilisateur_id')
            
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
            return jsonify(dict(new_report)), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur comptes_rendus: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
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
            return jsonify({'message': 'Compte rendu modifié'})
        
        elif request.method == 'DELETE':
            cur.execute('DELETE FROM comptes_rendus WHERE user_id = %s AND id = %s', (user_id, id))
            conn.commit()
            return jsonify({'message': 'Compte rendu supprimé'})
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur compte_rendu_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/comptes-rendus/<int:id>/data', methods=['GET'])
def get_compte_rendu_data(id):
    """
    Endpoint optimisé qui retourne uniquement les données du compte rendu
    La génération du PDF se fait côté client
    """
    user_id = request.headers.get('X-User-ID') or request.args.get('user_id')
    
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT cr.*,
                   p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                   m.nom as medecin_nom, m.specialite as medecin_specialite,
                   u.nom as utilisateur_nom
            FROM comptes_rendus cr
            LEFT JOIN patients p ON cr.patient_id = p.id
            LEFT JOIN medecins m ON cr.medecin_id = m.id
            LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero AND cr.user_id = u.user_id
            WHERE cr.user_id = %s AND cr.id = %s
        ''', (user_id, id))
        
        report = cur.fetchone()
        
        if not report:
            return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
        
        # Retourner les données au format JSON
        return jsonify({
            'id': report['id'],
            'numero_enregistrement': report['numero_enregistrement'],
            'date_compte_rendu': report['date_compte_rendu'],
            'date_prelevement': report['date_prelevement'],
            'date_reception': report.get('date_reception', ''),
            'service_hospitalier': report.get('service_hospitalier', ''),
            'nature_prelevement': report['nature_prelevement'],
            'renseignements_cliniques': report.get('renseignements_cliniques', ''),
            'macroscopie': report.get('macroscopie', ''),
            'microscopie': report.get('microscopie', ''),
            'conclusion': report.get('conclusion', ''),
            'statut': report['statut'],
            'patient': {
                'nom': report['patient_nom'] or 'Non renseigné',
                'age': report['patient_age'] or '',
                'sexe': report['patient_sexe'] or ''
            },
            'medecin': {
                'nom': report['medecin_nom'] or 'Non renseigné',
                'specialite': report.get('medecin_specialite', '')
            },
            'utilisateur': {
                'nom': report['utilisateur_nom'] or 'Non renseigné'
            }
        }), 200
        
    except Exception as e:
        print(f"[ERREUR] Récupération CR {id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'erreur': f'Erreur lors de la récupération: {str(e)}'}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================
# ENDPOINTS TEMPLATES - COMPLET
# ============================================

# GET: Liste tous les templates
@app.route('/api/templates', methods=['GET'])
def get_templates():
    user_id = request.headers.get('X-User-ID')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM templates 
        WHERE user_id = %s OR user_id = 'system'
        ORDER BY titre
    """, (user_id,))
    
    templates = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(templates)

# GET: Un template par ID
@app.route('/api/templates/<int:id>', methods=['GET'])
def get_template_by_id(id):
    user_id = request.headers.get('X-User-ID')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM templates 
        WHERE id = %s AND (user_id = %s OR user_id = 'system')
    """, (id, user_id))
    
    template = cur.fetchone()
    cur.close()
    conn.close()
    
    if not template:
        return jsonify({'erreur': 'Template non trouvé'}), 404
    return jsonify(template)

# POST: Créer un template
@app.route('/api/templates', methods=['POST'])
def create_template():
    user_id = request.headers.get('X-User-ID')
    data = request.json
    
    if not data.get('code') or not data.get('titre'):
        return jsonify({'erreur': 'Code et titre requis'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO templates 
            (code, user_id, titre, organe, tags, 
             renseignements_cliniques, macroscopie, microscopie, conclusion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['code'], user_id, data['titre'],
            data.get('organe'), data.get('tags', []),
            data.get('renseignements_cliniques', ''),
            data.get('macroscopie', ''), data.get('microscopie', ''),
            data.get('conclusion', '')
        ))
        
        new_id = cur.fetchone()['id']
        conn.commit()
        return jsonify({'success': True, 'id': new_id}), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'erreur': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# PUT: Modifier un template
@app.route('/api/templates/<int:id>', methods=['PUT'])
def update_template(id):
    user_id = request.headers.get('X-User-ID')
    data = request.json
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE templates SET
                code = COALESCE(%s, code),
                titre = COALESCE(%s, titre),
                organe = %s,
                tags = %s,
                renseignements_cliniques = %s,
                macroscopie = %s,
                microscopie = %s,
                conclusion = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND (user_id = %s OR user_id = 'system')
            RETURNING id
        """, (
            data.get('code'), data.get('titre'),
            data.get('organe'), data.get('tags', []),
            data.get('renseignements_cliniques', ''),
            data.get('macroscopie', ''), data.get('microscopie', ''),
            data.get('conclusion', ''),
            id, user_id
        ))
        
        if not cur.fetchone():
            conn.rollback()
            return jsonify({'erreur': 'Template non trouvé'}), 404
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'erreur': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# DELETE: Supprimer un template
@app.route('/api/templates/<int:id>', methods=['DELETE'])
def delete_template(id):
    user_id = request.headers.get('X-User-ID')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            DELETE FROM templates 
            WHERE id = %s AND (user_id = %s OR user_id = 'system')
            RETURNING id
        """, (id, user_id))
        
        if not cur.fetchone():
            conn.rollback()
            return jsonify({'erreur': 'Template non trouvé'}), 404
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'erreur': str(e)}), 500
    finally:
        cur.close()
        conn.close()
# ENDPOINTS CORRIGÉS - GESTION PAIEMENTS ESPÈCE ET À TERME

@app.route('/paiements', methods=['GET', 'POST'])
def paiements():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        if request.method == 'GET':
            # Récupérer les paramètres de filtrage
            patient_id = request.args.get('patient_id')
            date_debut = request.args.get('date_debut')
            date_fin = request.args.get('date_fin')
            mode_paiement = request.args.get('mode_paiement')
            type_paiement = request.args.get('type_paiement')
            
            # Construction de la requête SQL dynamique
            query = '''
                SELECT 
                    p.*,
                    pat.nom as patient_nom,
                    pat.telephone as patient_telephone,
                    u.nom as utilisateur_nom
                FROM paiements p
                LEFT JOIN patients pat ON p.patient_id = pat.id AND p.user_id = pat.user_id
                LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
                WHERE p.user_id = %s
            '''
            
            params = [user_id]
            
            # Ajout des filtres conditionnels
            if patient_id:
                query += ' AND p.patient_id = %s'
                params.append(patient_id)
            
            if date_debut:
                query += ' AND DATE(p.date_paiement) >= %s'
                params.append(date_debut)
            
            if date_fin:
                query += ' AND DATE(p.date_paiement) <= %s'
                params.append(date_fin)
            
            if mode_paiement:
                query += ' AND p.mode_paiement = %s'
                params.append(mode_paiement)
            
            if type_paiement:
                query += ' AND p.type_paiement = %s'
                params.append(type_paiement)
            
            query += ' ORDER BY p.date_paiement DESC'
            
            # Pagination
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            offset = (page - 1) * per_page
            
            # D'abord, compter le total
            count_query = '''
                SELECT COUNT(*) as total
                FROM paiements p
                LEFT JOIN patients pat ON p.patient_id = pat.id AND p.user_id = pat.user_id
                LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
                WHERE p.user_id = %s
            '''
            
            count_params = [user_id]
            
            # Ajouter les mêmes filtres pour le count
            if patient_id:
                count_query += ' AND p.patient_id = %s'
                count_params.append(patient_id)
            
            if date_debut:
                count_query += ' AND DATE(p.date_paiement) >= %s'
                count_params.append(date_debut)
            
            if date_fin:
                count_query += ' AND DATE(p.date_paiement) <= %s'
                count_params.append(date_fin)
            
            if mode_paiement:
                count_query += ' AND p.mode_paiement = %s'
                count_params.append(mode_paiement)
            
            if type_paiement:
                count_query += ' AND p.type_paiement = %s'
                count_params.append(type_paiement)
            
            cur.execute(count_query, count_params)
            total_result = cur.fetchone()
            total_count = total_result['total'] if total_result else 0
            
            # Ajouter la pagination à la requête principale
            query += ' LIMIT %s OFFSET %s'
            params.extend([per_page, offset])
            
            cur.execute(query, params)
            payments = cur.fetchall()
            
            # Formater les résultats
            formatted_payments = []
            for p in payments:
                payment_dict = dict(p)
                
                # Créer le nom complet du patient (uniquement avec nom)
                payment_dict['patient_nom_complet'] = p['patient_nom'] or 'Patient inconnu'
                
                # Convertir les montants en float
                payment_dict['montant'] = float(p['montant']) if p['montant'] else 0
                if p['montant_total']:
                    payment_dict['montant_total'] = float(p['montant_total'])
                
                # Formater la date
                if p['date_paiement']:
                    payment_dict['date_paiement_formatted'] = p['date_paiement'].strftime('%d/%m/%Y %H:%M')
                
                formatted_payments.append(payment_dict)
            
            return jsonify({
                'paiements': formatted_payments,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'total_pages': (total_count + per_page - 1) // per_page if per_page > 0 else 1
                }
            })
        
        elif request.method == 'POST':
            data = request.json
            required = ['patient_id', 'montant', 'type_paiement', 'mode_paiement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            montant_paye = float(data['montant'])
            mode_paiement = data['mode_paiement']
            
            # Récupérer le patient
            cur.execute('''
                SELECT nom, solde FROM patients 
                WHERE id = %s AND user_id = %s
            ''', (data['patient_id'], user_id))
            
            patient = cur.fetchone()
            if not patient:
                return jsonify({'erreur': 'Patient non trouvé'}), 404
            
            solde_actuel = float(patient['solde'] or 0)
            
            # Pour les paiements à terme, vérifier le montant total
            montant_total = None
            if mode_paiement == 'a_terme':
                montant_total = float(data.get('montant_total', 0))
                if montant_total <= montant_paye:
                    return jsonify({'erreur': 'Le montant total doit être supérieur au montant payé pour un paiement à terme'}), 400
            
            # Récupérer l'utilisateur connecté
            utilisateur_id = data.get('utilisateur_id')
            
            # Insérer le paiement
            cur.execute('''
                INSERT INTO paiements (
                    user_id, patient_id, utilisateur_id, montant, 
                    type_paiement, mode_paiement, montant_total,
                    numero_cr, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, date_paiement
            ''', (
                user_id,
                data['patient_id'],
                utilisateur_id,
                montant_paye,
                data['type_paiement'],
                mode_paiement,
                montant_total,
                data.get('numero_cr'),
                data.get('notes')
            ))
            
            new_payment = cur.fetchone()
            
            # Calculer le nouveau solde selon le mode de paiement
            if mode_paiement == 'a_terme':
                reste_a_payer = montant_total - montant_paye
                nouveau_solde = solde_actuel - reste_a_payer
                message = f'Paiement à terme enregistré. Reste à payer: {reste_a_payer:.2f} DA'
            elif mode_paiement == 'paiement_partiel':
                # Pour un paiement partiel, on réduit la dette (solde négatif)
                nouveau_solde = solde_actuel + montant_paye
                message = f'Paiement partiel enregistré. Nouveau solde: {nouveau_solde:.2f} DA'
            else:  # espece (comptant)
                # Pour un paiement comptant, on augmente le solde (crédit positif)
                nouveau_solde = solde_actuel + montant_paye
                message = f'Paiement comptant enregistré. Nouveau solde: {nouveau_solde:.2f} DA'
            
            # Mettre à jour le solde du patient
            cur.execute('''
                UPDATE patients 
                SET solde = %s
                WHERE id = %s AND user_id = %s
            ''', (nouveau_solde, data['patient_id'], user_id))
            
            conn.commit()
            
            result = dict(new_payment)
            result['nouveau_solde'] = nouveau_solde
            result['message'] = message
            
            return jsonify(result), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur paiements: {str(e)}")
        traceback.print_exc()
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
@app.route('/paiements/paiement-partiel', methods=['POST'])
def paiement_partiel():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    required = ['patient_id', 'montant']
    
    if not data or any(k not in data for k in required):
        return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        montant_paye = float(data['montant'])
        
        # Récupérer le patient
        cur.execute('''
            SELECT nom, solde FROM patients 
            WHERE id = %s AND user_id = %s
        ''', (data['patient_id'], user_id))
        
        patient = cur.fetchone()
        if not patient:
            return jsonify({'erreur': 'Patient non trouvé'}), 404
        
        solde_actuel = float(patient['solde'] or 0)
        
        # Calculer le nouveau solde
        nouveau_solde = solde_actuel + montant_paye
        dette_reglee = nouveau_solde >= 0
        
        # Éviter un solde positif pour une dette
        if nouveau_solde > 0:
            nouveau_solde = 0
        
        # Récupérer l'utilisateur
        selected_user = None
        try:
            selected_user_str = request.headers.get('X-Selected-User')
            if selected_user_str:
                selected_user = json.loads(selected_user_str)
        except:
            pass
        
        utilisateur_id = selected_user.get('numero') if selected_user else None
        
        # Insérer le paiement
        cur.execute('''
            INSERT INTO paiements (
                user_id, patient_id, utilisateur_id, montant, 
                type_paiement, mode_paiement, numero_cr, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, date_paiement
        ''', (
            user_id,
            data['patient_id'],
            utilisateur_id,
            montant_paye,
            data.get('type_paiement', 'consultation'),
            'paiement_partiel',
            data.get('numero_cr'),
            data.get('notes')
        ))
        
        new_payment = cur.fetchone()
        
        # Mettre à jour le solde du patient
        cur.execute('''
            UPDATE patients 
            SET solde = %s
            WHERE id = %s AND user_id = %s
        ''', (nouveau_solde, data['patient_id'], user_id))
        
        conn.commit()
        
        result = dict(new_payment)
        result['nouveau_solde'] = nouveau_solde
        result['dette_reglee'] = dette_reglee
        
        if dette_reglee:
            result['message'] = 'Dette entièrement réglée'
        else:
            result['message'] = f'Paiement partiel enregistré. Dette restante: {abs(nouveau_solde):.2f} DA'
        
        return jsonify(result), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur paiement_partiel: {str(e)}")
        traceback.print_exc()
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
@app.route('/paiements/<int:id>', methods=['GET', 'DELETE'])
def paiement_detail(id):
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
                SELECT 
                    p.*,
                    pat.nom as patient_nom,
                    pat.telephone as patient_telephone,
                    pat.solde as patient_solde,
                    u.nom as utilisateur_nom
                FROM paiements p
                LEFT JOIN patients pat ON p.patient_id = pat.id AND p.user_id = pat.user_id
                LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
                WHERE p.user_id = %s AND p.id = %s
            ''', (user_id, id))
            
            payment = cur.fetchone()
            if not payment:
                return jsonify({'erreur': 'Paiement non trouvé'}), 404
            
            # Formater le résultat
            result = dict(payment)
            
            # Nom du patient
            result['patient_nom_complet'] = payment['patient_nom'] or 'Patient inconnu'
            
            # Convertir les montants
            result['montant'] = float(payment['montant']) if payment['montant'] else 0
            if payment['montant_total']:
                result['montant_total'] = float(payment['montant_total'])
            
            # Formater la date
            if payment['date_paiement']:
                result['date_paiement_formatted'] = payment['date_paiement'].strftime('%d/%m/%Y %H:%M')
            
            return jsonify(result)
        
        elif request.method == 'DELETE':
            # Récupérer d'abord le paiement
            cur.execute('''
                SELECT patient_id, montant, mode_paiement FROM paiements 
                WHERE user_id = %s AND id = %s
            ''', (user_id, id))
            
            payment = cur.fetchone()
            if not payment:
                return jsonify({'erreur': 'Paiement non trouvé'}), 404
            
            # Supprimer le paiement
            cur.execute('''
                DELETE FROM paiements 
                WHERE user_id = %s AND id = %s
            ''', (user_id, id))
            
            # Recalculer le solde du patient
            if payment['patient_id']:
                cur.execute('''
                    SELECT COALESCE(SUM(montant), 0) as total_paye FROM paiements
                    WHERE user_id = %s AND patient_id = %s
                ''', (user_id, payment['patient_id']))
                
                total_result = cur.fetchone()
                total_paye = float(total_result['total_paye'] or 0)
                
                # Mettre à jour le solde
                cur.execute('''
                    UPDATE patients 
                    SET solde = %s
                    WHERE id = %s AND user_id = %s
                ''', (total_paye, payment['patient_id'], user_id))
            
            conn.commit()
            return jsonify({'message': 'Paiement supprimé avec succès'})
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur paiement_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()           
@app.route('/paiements/statistiques', methods=['GET'])
def statistiques_paiements():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Statistiques générales
        stats_query = '''
            SELECT 
                COUNT(*) as total_paiements,
                SUM(montant) as total_montant,
                AVG(montant) as moyenne_montant,
                MIN(montant) as minimum_montant,
                MAX(montant) as maximum_montant,
                COUNT(DISTINCT patient_id) as patients_uniques
            FROM paiements
            WHERE user_id = %s
        '''
        stats_params = [user_id]
        
        if date_debut:
            stats_query += ' AND date_paiement >= %s'
            stats_params.append(date_debut)
        
        if date_fin:
            stats_query += ' AND date_paiement <= %s'
            stats_params.append(date_fin)
        
        cur.execute(stats_query, stats_params)
        stats = cur.fetchone()
        
        # Statistiques par mode de paiement
        mode_query = '''
            SELECT 
                mode_paiement,
                COUNT(*) as nombre,
                SUM(montant) as total
            FROM paiements
            WHERE user_id = %s
        '''
        mode_params = [user_id]
        
        if date_debut:
            mode_query += ' AND date_paiement >= %s'
            mode_params.append(date_debut)
        
        if date_fin:
            mode_query += ' AND date_paiement <= %s'
            mode_params.append(date_fin)
        
        mode_query += ' GROUP BY mode_paiement ORDER BY total DESC'
        
        cur.execute(mode_query, mode_params)
        par_mode = cur.fetchall()
        
        # Statistiques par type de paiement
        type_query = '''
            SELECT 
                type_paiement,
                COUNT(*) as nombre,
                SUM(montant) as total
            FROM paiements
            WHERE user_id = %s
        '''
        type_params = [user_id]
        
        if date_debut:
            type_query += ' AND date_paiement >= %s'
            type_params.append(date_debut)
        
        if date_fin:
            type_query += ' AND date_paiement <= %s'
            type_params.append(date_fin)
        
        type_query += ' GROUP BY type_paiement ORDER BY total DESC'
        
        cur.execute(type_query, type_params)
        par_type = cur.fetchall()
        
        # Évolution mensuelle
        evolution_query = '''
            SELECT 
                TO_CHAR(date_paiement, 'YYYY-MM') as mois,
                COUNT(*) as nombre_paiements,
                SUM(montant) as total_montant
            FROM paiements
            WHERE user_id = %s
        '''
        evolution_params = [user_id]
        
        if date_debut:
            evolution_query += ' AND date_paiement >= %s'
            evolution_params.append(date_debut)
        
        if date_fin:
            evolution_query += ' AND date_paiement <= %s'
            evolution_params.append(date_fin)
        
        evolution_query += '''
            GROUP BY TO_CHAR(date_paiement, 'YYYY-MM')
            ORDER BY mois DESC
            LIMIT 12
        '''
        
        cur.execute(evolution_query, evolution_params)
        evolution = cur.fetchall()
        
        # Top 10 patients par montant payé
        top_patients_query = '''
            SELECT 
                p.patient_id,
                pat.nom,
                COUNT(p.id) as nombre_paiements,
                SUM(p.montant) as total_paye
            FROM paiements p
            LEFT JOIN patients pat ON p.patient_id = pat.id AND p.user_id = pat.user_id
            WHERE p.user_id = %s
        '''
        top_params = [user_id]
        
        if date_debut:
            top_patients_query += ' AND p.date_paiement >= %s'
            top_params.append(date_debut)
        
        if date_fin:
            top_patients_query += ' AND p.date_paiement <= %s'
            top_params.append(date_fin)
        
        top_patients_query += '''
            GROUP BY p.patient_id, pat.nom
            ORDER BY total_paye DESC
            LIMIT 10
        '''
        
        cur.execute(top_patients_query, top_params)
        top_patients = cur.fetchall()
        
        return jsonify({
            'statistiques_generales': dict(stats) if stats else {},
            'par_mode_paiement': [dict(m) for m in par_mode],
            'par_type_paiement': [dict(t) for t in par_type],
            'evolution_mensuelle': [dict(e) for e in evolution],
            'top_patients': [dict(t) for t in top_patients]
        })
        
    except Exception as e:
        print(f"❌ Erreur statistiques_paiements: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/paiements/dettes-actives', methods=['GET'])
def dettes_actives():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Récupérer tous les patients avec solde négatif (dette)
        cur.execute('''
            SELECT 
                p.id,
                p.nom,
                p.telephone,
                p.age,
                p.sexe,
                p.solde,
                COUNT(pa.id) as nombre_paiements,
                MAX(pa.date_paiement) as dernier_paiement
            FROM patients p
            LEFT JOIN paiements pa ON p.id = pa.patient_id AND p.user_id = pa.user_id
            WHERE p.user_id = %s 
            AND p.solde < 0
            GROUP BY p.id, p.nom, p.telephone, p.age, p.sexe, p.solde
            ORDER BY ABS(p.solde) DESC
        ''', (user_id,))
        
        dettes = cur.fetchall()
        
        # Formater les résultats
        dettes_formatees = []
        for d in dettes:
            dette = dict(d)
            dette['montant_dette'] = abs(float(d['solde'])) if d['solde'] else 0
            
            # Nom du patient (sans prenom)
            dette['nom_complet'] = d['nom']
            
            dettes_formatees.append(dette)
        
        return jsonify(dettes_formatees)
        
    except Exception as e:
        print(f"❌ Erreur dettes_actives: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
@app.route('/paiements/statistiques-dettes', methods=['GET'])
def statistiques_dettes():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Statistiques des dettes
        cur.execute('''
            SELECT 
                COUNT(*) as nombre_patients_dette,
                SUM(ABS(solde)) as montant_total_dettes,
                AVG(ABS(solde)) as moyenne_dette,
                MAX(ABS(solde)) as dette_maximale
            FROM patients 
            WHERE user_id = %s AND solde < 0
        ''', (user_id,))
        
        stats = cur.fetchone()
        
        # Derniers paiements partiels
        cur.execute('''
            SELECT 
                pa.id,
                pa.date_paiement,
                pa.montant,
                p.nom as patient_nom
            FROM paiements pa
            JOIN patients p ON pa.patient_id = p.id AND pa.user_id = p.user_id
            WHERE pa.user_id = %s 
            AND pa.mode_paiement = 'paiement_partiel'
            ORDER BY pa.date_paiement DESC
            LIMIT 10
        ''', (user_id,))
        
        derniers_paiements = cur.fetchall()
        
        return jsonify({
            'statistiques': dict(stats) if stats else {},
            'derniers_paiements_partiels': [dict(p) for p in derniers_paiements]
        })
        
    except Exception as e:
        print(f"❌ Erreur statistiques_dettes: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/paiements/rapport-journalier', methods=['GET'])
def rapport_journalier():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    date = request.args.get('date')
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Paiements de la journée
        cur.execute('''
            SELECT 
                p.*,
                pat.nom as patient_nom,
                pat.telephone as patient_telephone,
                u.nom as utilisateur_nom
            FROM paiements p
            LEFT JOIN patients pat ON p.patient_id = pat.id AND p.user_id = pat.user_id
            LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
            WHERE p.user_id = %s 
            AND DATE(p.date_paiement) = %s
            ORDER BY p.date_paiement
        ''', (user_id, date))
        
        paiements = cur.fetchall()
        
        # Totaux par mode
        cur.execute('''
            SELECT 
                mode_paiement,
                COUNT(*) as nombre,
                SUM(montant) as total
            FROM paiements
            WHERE user_id = %s 
            AND DATE(date_paiement) = %s
            GROUP BY mode_paiement
        ''', (user_id, date))
        
        totaux_par_mode = cur.fetchall()
        
        total_general = sum(float(p['montant']) for p in paiements if p['montant'])
        
        return jsonify({
            'date': date,
            'paiements': [dict(p) for p in paiements],
            'totaux_par_mode': [dict(t) for t in totaux_par_mode],
            'total_general': total_general,
            'nombre_paiements': len(paiements)
        })
        
    except Exception as e:
        print(f"❌ Erreur rapport_journalier: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/paiements/synthese-patient/<int:patient_id>', methods=['GET'])
def synthese_patient(patient_id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Informations du patient
        cur.execute('''
            SELECT nom, telephone, age, sexe, solde, adresse
            FROM patients
            WHERE id = %s AND user_id = %s
        ''', (patient_id, user_id))
        
        patient = cur.fetchone()
        if not patient:
            return jsonify({'erreur': 'Patient non trouvé'}), 404
        
        # Tous les paiements du patient
        cur.execute('''
            SELECT 
                p.*,
                u.nom as utilisateur_nom
            FROM paiements p
            LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
            WHERE p.patient_id = %s AND p.user_id = %s
            ORDER BY p.date_paiement DESC
        ''', (patient_id, user_id))
        
        paiements = cur.fetchall()
        
        # Calculer les statistiques
        total_paye = sum(float(p['montant']) for p in paiements if p['montant'])
        paiements_a_terme = [p for p in paiements if p['mode_paiement'] == 'a_terme']
        paiements_partiels = [p for p in paiements if p['mode_paiement'] == 'paiement_partiel']
        dernier_paiement = paiements[0] if paiements else None
        
        # Détails des paiements à terme
        details_a_terme = []
        for p in paiements_a_terme:
            if p['montant_total']:
                reste = float(p['montant_total']) - float(p['montant'])
                details_a_terme.append({
                    'id': p['id'],
                    'date': p['date_paiement'].strftime('%d/%m/%Y') if p['date_paiement'] else None,
                    'montant_paye': float(p['montant']),
                    'montant_total': float(p['montant_total']),
                    'reste_a_payer': reste,
                    'numero_cr': p['numero_cr']
                })
        
        return jsonify({
            'patient': dict(patient),
            'paiements': [dict(p) for p in paiements],
            'statistiques': {
                'nombre_total_paiements': len(paiements),
                'total_paye': total_paye,
                'nombre_paiements_a_terme': len(paiements_a_terme),
                'nombre_paiements_partiels': len(paiements_partiels),
                'solde_actuel': float(patient['solde']) if patient['solde'] else 0,
                'dernier_paiement': dict(dernier_paiement) if dernier_paiement else None
            },
            'details_a_terme': details_a_terme
        })
        
    except Exception as e:
        print(f"❌ Erreur synthese_patient: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()  
# ================================================
# HISTORIQUE DES PAIEMENTS D'UN PATIENT
# ================================================
@app.route('/paiements/patient/<int:patient_id>', methods=['GET'])
def historique_patient_paiements(patient_id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Vérifier d'abord que le patient existe et appartient à l'utilisateur
        cur.execute('''
            SELECT id, nom FROM patients 
            WHERE id = %s AND user_id = %s
        ''', (patient_id, user_id))
        
        patient = cur.fetchone()
        if not patient:
            return jsonify({'erreur': 'Patient non trouvé'}), 404
        
        # Récupérer tous les paiements du patient
        cur.execute('''
            SELECT 
                p.*,
                u.nom as utilisateur_nom
            FROM paiements p
            LEFT JOIN utilisateurs u ON p.utilisateur_id = u.numero AND p.user_id = u.user_id
            WHERE p.patient_id = %s AND p.user_id = %s
            ORDER BY p.date_paiement DESC
        ''', (patient_id, user_id))
        
        paiements = cur.fetchall()
        
        # Formater les résultats
        paiements_formates = []
        for paiement in paiements:
            paiement_dict = dict(paiement)
            
            # Convertir les montants
            paiement_dict['montant'] = float(paiement['montant']) if paiement['montant'] else 0
            if paiement['montant_total']:
                paiement_dict['montant_total'] = float(paiement['montant_total'])
            
            # Formater les dates
            if paiement['date_paiement']:
                paiement_dict['date_paiement_formatted'] = paiement['date_paiement'].strftime('%d/%m/%Y')
            
            paiements_formates.append(paiement_dict)
        
        return jsonify({
            'patient': dict(patient),
            'paiements': paiements_formates,
            'nombre_paiements': len(paiements_formates)
        })
        
    except Exception as e:
        print(f"❌ Erreur historique_patient_paiements: {str(e)}")
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
 #   try:
  #      init_db()
  #  except Exception as e:
  #      print(f"?? Avertissement init_db: {str(e)}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
