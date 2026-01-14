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
