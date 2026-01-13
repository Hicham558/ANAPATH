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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm


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

@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
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
        
        # === GÉNÉRATION DU PDF DANS LE STYLE ANAPATH ELYOUSR ===
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4,
            rightMargin=40,    # Marges réduites pour plus d'espace
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # === STYLES PERSONNALISÉS ===
        # Style pour en-tête principal
        entete_principal_style = ParagraphStyle(
            'EntetePrincipal',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            textColor=colors.black,
            alignment=1,  # Centré
            spaceAfter=4
        )
        
        # Style pour sous-titre
        sous_titre_style = ParagraphStyle(
            'SousTitre',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            textColor=colors.black,
            alignment=1,
            spaceAfter=16
        )
        
        # Style pour informations patient/médecin
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.black,
            leading=12
        )
        
        # Style pour étiquettes (labels)
        label_style = ParagraphStyle(
            'LabelStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.black,
            leading=12
        )
        
        # Style pour titre principal du CR
        titre_cr_style = ParagraphStyle(
            'TitreCR',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=colors.black,
            alignment=1,
            spaceBefore=20,
            spaceAfter=20,
            borderWidth=1,
            borderColor=colors.black,
            borderPadding=(10, 5, 10, 5)
        )
        
        # Style pour sections (MACROSCOPIE, MICROSCOPIE, CONCLUSION)
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=colors.black,
            spaceBefore=15,
            spaceAfter=8,
            leftIndent=0
        )
        
        # Style pour contenu des sections
        contenu_style = ParagraphStyle(
            'ContenuStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.black,
            leftIndent=20,
            leading=14,
            spaceAfter=5
        )
        
        # Style pour signature
        signature_style = ParagraphStyle(
            'SignatureStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.black,
            alignment=2,  # Aligné à droite
            spaceBefore=40
        )
        
        # === CONSTRUCTION DU DOCUMENT ===
        
        # 1. EN-TÊTE ANAPATH ELYOUSR
        story.append(Paragraph("<b>ANAPATH ELYOUSR</b>", entete_principal_style))
        story.append(Paragraph("<b>LABORATOIRE D'ANATOMIE & DE CYTOLOGIE PATHOLOGIQUES</b>", sous_titre_style))
        story.append(Paragraph("<b>Dr. BENFOULA Amel épouse ERROUANE</b>", sous_titre_style))
        
        story.append(Spacer(1, 20))
        
        # 2. TABLEAU DES INFORMATIONS (comme dans le document Word)
        # Première ligne
        info_data1 = [
            [
                Paragraph("<b>N d'enregistrement :</b>", label_style),
                Paragraph(f"{report['numero_enregistrement']}", info_style),
                Paragraph("<b>Médecin Demandeur :</b>", label_style),
                Paragraph(f"{report['medecin_nom'] or 'Non renseigné'}", info_style),
                Paragraph("<b>Date du Compte Rendu :</b>", label_style),
                Paragraph(f"{report['date_compte_rendu']}", info_style)
            ]
        ]
        
        table1 = Table(info_data1, colWidths=[3*cm, 4*cm, 3*cm, 4*cm, 3*cm, 3*cm])
        table1.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(table1)
        
        # Deuxième ligne
        info_data2 = [
            [
                Paragraph("<b>Service Hospitalier :</b>", label_style),
                Paragraph(f"{report.get('service_hospitalier', '-')}", info_style),
                Paragraph("<b>PATIENT :</b>", label_style),
                Paragraph("<b>Nom & Prénom :</b>", label_style),
                Paragraph(f"{report['patient_nom'] or 'Non renseigné'}", info_style),
                Paragraph("<b>Age :</b>", label_style),
                Paragraph(f"{report['patient_age'] or '-'}", info_style),
                Paragraph("<b>Sexe :</b>", label_style),
                Paragraph(f"{'M' if report['patient_sexe'] == 'M' else 'F' if report['patient_sexe'] == 'F' else '-'}", info_style)
            ]
        ]
        
        table2 = Table(info_data2, colWidths=[2.5*cm, 4*cm, 2*cm, 2*cm, 3.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm])
        table2.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(table2)
        
        # Troisième ligne
        info_data3 = [
            [
                Paragraph("<b>Nature / Siège du Prélèvement :</b>", label_style),
                Paragraph(f"{report['nature_prelevement'] or 'Non renseigné'}", info_style),
                Paragraph("<b>Date Prélèvement :</b>", label_style),
                Paragraph(f"{report['date_prelevement'] or '-'}", info_style),
                Paragraph("<b>Réception :</b>", label_style),
                Paragraph(f"{report.get('date_reception', '-')}", info_style)
            ]
        ]
        
        table3 = Table(info_data3, colWidths=[4*cm, 6*cm, 3*cm, 3*cm, 2*cm, 3*cm])
        table3.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(table3)
        
        story.append(Spacer(1, 15))
        
        # 3. RENSEIGNEMENTS CLINIQUES
        if report.get('renseignements_cliniques'):
            story.append(Paragraph("<b>Renseignements Cliniques Fournis :</b>", label_style))
            story.append(Spacer(1, 5))
            
            # Gestion du texte avec sauts de ligne
            renseignements = str(report['renseignements_cliniques']).strip()
            if renseignements:
                for line in renseignements.split('\n'):
                    if line.strip():
                        story.append(Paragraph(line.strip(), contenu_style))
            else:
                story.append(Paragraph("-", contenu_style))
            
            story.append(Spacer(1, 15))
        
        # 4. TITRE PRINCIPAL
        story.append(Paragraph("COMPTE RENDU CYTO-PATHOLOGIQUE", titre_cr_style))
        
        # 5. MACROSCOPIE
        if report.get('macroscopie'):
            story.append(Paragraph("MACROSCOPIE :", section_style))
            story.append(Spacer(1, 5))
            
            macroscopie_text = str(report['macroscopie']).strip()
            if macroscopie_text:
                # Formater avec tirets comme dans le document Word
                lines = macroscopie_text.split('\n')
                for line in lines:
                    if line.strip():
                        if line.strip().startswith('-'):
                            story.append(Paragraph(line.strip(), contenu_style))
                        else:
                            story.append(Paragraph(f"- {line.strip()}", contenu_style))
            else:
                story.append(Paragraph("-", contenu_style))
            
            story.append(Spacer(1, 10))
        
        # 6. MICROSCOPIE
        if report.get('microscopie'):
            story.append(Paragraph("MICROSCOPIE :", section_style))
            story.append(Spacer(1, 5))
            
            microscopie_text = str(report['microscopie']).strip()
            if microscopie_text:
                # Conserver la mise en forme originale
                lines = microscopie_text.split('\n')
                for line in lines:
                    if line.strip():
                        story.append(Paragraph(line.strip(), contenu_style))
            else:
                story.append(Paragraph("-", contenu_style))
            
            story.append(Spacer(1, 10))
        
        # 7. CONCLUSION
        if report.get('conclusion'):
            story.append(Paragraph("CONCLUSION :", section_style))
            story.append(Spacer(1, 5))
            
            conclusion_text = str(report['conclusion']).strip()
            if conclusion_text:
                lines = conclusion_text.split('\n')
                for line in lines:
                    if line.strip():
                        # Style spécial pour les lignes importantes
                        if line.strip().upper().startswith(('ASPECT', 'DIAGNOSTIC', 'RECOMMANDATION', 'CATÉGORIE', 'CLASSIFICATION')):
                            bold_style = ParagraphStyle(
                                'ConclusionBold',
                                parent=contenu_style,
                                fontName='Helvetica-Bold'
                            )
                            story.append(Paragraph(line.strip(), bold_style))
                        else:
                            story.append(Paragraph(line.strip(), contenu_style))
            else:
                story.append(Paragraph("-", contenu_style))
        
        # 8. SIGNATURE
        story.append(Spacer(1, 30))
        
        signature_text = '''
        <b>Confraternellement</b><br/>
        Dr. BENFOULA Amel
        '''
        story.append(Paragraph(signature_text, signature_style))
        
        # 9. INFORMATIONS DE BAS DE PAGE
        story.append(Spacer(1, 30))
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            textColor=colors.grey,
            alignment=1
        )
        
        footer_text = f'''
        Document généré le {datetime.now().strftime('%d/%m/%Y %H:%M')} | 
        Compte rendu N° {report['numero_enregistrement']} |
        Page <page/>
        '''
        story.append(Paragraph(footer_text, footer_style))
        
        # === CONSTRUCTION FINALE ===
        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
        buffer.seek(0)
        
        # Nom du fichier PDF
        nom_fichier = f"CR_{report['numero_enregistrement']}_{report['patient_nom'].replace(' ', '_') if report['patient_nom'] else id}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=nom_fichier,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"[ERREUR PDF] CR {id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'erreur': f'Erreur génération PDF: {str(e)}'}), 500
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def add_page_number(canvas, doc):
    """Ajoute le numéro de page au PDF"""
    page_num = canvas.getPageNumber()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(
        doc.pagesize[0] - 40,  # Position X
        30,                     # Position Y
        f"Page {page_num}"
    )

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
  #  try:
  #      init_db()
  #  except Exception as e:
  #      print(f"?? Avertissement init_db: {str(e)}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
