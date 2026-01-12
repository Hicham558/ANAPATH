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
        
        # === NOUVELLE FONCTIONNALITÉ : GÉNÉRATION AVANCÉE ===
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4,
            rightMargin=72,  # 1 inch = 72 points
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Styles professionnels
        styles = getSampleStyleSheet()
        
        # Style personnalisé pour en-tête
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            alignment=1,  # TA_CENTER
            spaceAfter=12
        )
        
        # Style pour sous-titre
        subheader_style = ParagraphStyle(
            'SubHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=colors.HexColor('#2c3e50'),
            alignment=1,
            spaceAfter=6
        )
        
        # Style pour les sections
        section_style = ParagraphStyle(
            'Section',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=colors.black,
            leftIndent=0,
            spaceBefore=12,
            spaceAfter=6,
            borderWidth=1,
            borderColor=colors.HexColor('#3498db'),
            borderPadding=(3, 6, 3, 6),
            borderRadius=2,
            backgroundColor=colors.HexColor('#f8f9fa')
        )
        
        # Style pour contenu
        content_style = ParagraphStyle(
            'Content',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.black,
            leftIndent=20,
            spaceAfter=6,
            leading=14  # Interligne
        )
        
        # Style pour signature
        signature_style = ParagraphStyle(
            'Signature',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=10,
            textColor=colors.grey,
            alignment=2,  # TA_RIGHT
            spaceBefore=40
        )
        
        # Construction du document
        story = []
        
        # === EN-TÊTE PROFESSIONNEL ===
        story.append(Paragraph("ANAPATH ELYOUSR", header_style))
        story.append(Paragraph("Laboratoire d'Anatomie & Cytologie Pathologiques", subheader_style))
        story.append(Paragraph("Dr. BENFOULA Amel épouse ERROUANE", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # === TITRE PRINCIPAL ===
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            textColor=colors.HexColor('#2980b9'),
            alignment=1,
            spaceAfter=20,
            borderWidth=1,
            borderColor=colors.HexColor('#2980b9'),
            borderPadding=5,
            borderRadius=3
        )
        story.append(Paragraph("COMPTE RENDU CYTO-PATHOLOGIQUE", title_style))
        
        # === TABLEAU D'INFORMATIONS ===
        info_data = [
            ['N° Enregistrement', report['numero_enregistrement'], 
             'Date Compte Rendu', report['date_compte_rendu']],
            ['Patient', report['patient_nom'] or 'Non renseigné', 
             'Âge/Sexe', f"{report['patient_age'] or '-'} ans / {report['patient_sexe'] or '-'}"],
            ['Médecin', f"{report['medecin_nom'] or 'Non renseigné'}<br/>{report.get('medecin_specialite', '')}", 
             'Service', report.get('service_hospitalier', '-')],
            ['Date Prélèvement', report['date_prelevement'] or '-', 
             'Utilisateur', report.get('utilisateur_nom', 'Non spécifié')],
        ]
        
        info_table = Table(info_data, colWidths=[4*cm, 7*cm, 3*cm, 6*cm])
        info_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f8ff')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 6),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))
        
        # === FONCTION POUR AJOUTER DES SECTIONS ===
        def add_section(title, content, style=content_style):
            # Titre de section
            story.append(Paragraph(title, section_style))
            
            # Contenu avec gestion des sauts de ligne
            if content and str(content).strip():
                # Conserver les sauts de ligne existants
                content_lines = str(content).split('\n')
                for line in content_lines:
                    if line.strip():
                        story.append(Paragraph(line.strip(), style))
                    else:
                        story.append(Spacer(1, 6))  # Espace pour ligne vide
            else:
                story.append(Paragraph("<i>Non renseigné</i>", 
                    ParagraphStyle('Italic', parent=styles['Normal'], fontName='Helvetica-Oblique')))
            
            story.append(Spacer(1, 12))
        
        # === SECTIONS DU COMPTE RENDU ===
        add_section("NATURE DU PRÉLÈVEMENT", report.get('nature_prelevement'))
        add_section("RENSEIGNEMENTS CLINIQUES", report.get('renseignements_cliniques'))
        add_section("MACROSCOPIE", report.get('macroscopie'))
        add_section("MICROSCOPIE", report.get('microscopie'))
        
        # Conclusion avec style spécial
        conclusion_style = ParagraphStyle(
            'Conclusion',
            parent=content_style,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#c0392b'),
            leftIndent=0,
            borderWidth=1,
            borderColor=colors.HexColor('#e74c3c'),
            borderPadding=10,
            backgroundColor=colors.HexColor('#fff5f5')
        )
        add_section("CONCLUSION", report.get('conclusion'), conclusion_style)
        
        # === SIGNATURE ===
        today = datetime.now().strftime('%d/%m/%Y')
        signature_text = f'''
        Fait à El Oued, le {today}<br/>
        _________________________<br/>
        <b>Dr. BENFOULA Amel épouse ERROUANE</b><br/>
        Anatomopathologiste
        '''
        story.append(Paragraph(signature_text, signature_style))
        
        # === PIED DE PAGE ===
        story.append(Spacer(1, 30))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            textColor=colors.grey,
            alignment=1  # Centré
        )
        
        footer_text = '''
        <b>Document généré électroniquement - Valable sans signature manuscrite</b><br/>
        Conservation obligatoire : 30 ans - N° RPPS : XXXXXXXXX<br/>
        Tél: XX XX XX XX XX - Email: contact@anapath-elyousr.dz
        '''
        story.append(Paragraph(footer_text, footer_style))
        
        # === GÉNÉRATION DU PDF ===
        doc.build(story)
        buffer.seek(0)
        
        # Journalisation
        print(f"[PRINT SUCCESS] PDF généré pour CR {id} - {report['numero_enregistrement']}")
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"CR_{report['numero_enregistrement']}_{today.replace('/', '-')}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"[PRINT ERROR] CR {id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'erreur': f'Erreur génération PDF: {str(e)}'}), 500
    
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
