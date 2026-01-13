from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
import gc
import traceback

# Configuration minimale pour réduire l'empreinte mémoire
os.environ['PYTHONHASHSEED'] = '0'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://hicham558.github.io", "http://localhost:*", "*"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-User-ID", "Authorization"],
    "supports_credentials": True,
    "max_age": 86400
}})

# Configuration mémoire optimisée
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # Désactive le formatage JSON joli
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# ================================================
# POOL DE CONNEXIONS BASIQUE
# ================================================
class ConnectionPool:
    """Pool de connexions simple pour réutiliser les connexions"""
    _connections = {}
    
    @classmethod
    def get_connection(cls, db_url):
        """Obtenir une connexion, en créer une si nécessaire"""
        if db_url not in cls._connections:
            try:
                cls._connections[db_url] = psycopg2.connect(
                    db_url, 
                    cursor_factory=RealDictCursor,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5
                )
            except Exception as e:
                print(f"❌ ERREUR CONNEXION DB: {str(e)}")
                raise
        return cls._connections[db_url]
    
    @classmethod
    def close_all(cls):
        """Fermer toutes les connexions"""
        for conn in cls._connections.values():
            try:
                conn.close()
            except:
                pass
        cls._connections.clear()

# ================================================
# CONTEXTE MANAGER POUR DB
# ================================================
class DBCursor:
    """Gestionnaire de contexte pour les opérations DB"""
    def __init__(self):
        self.conn = None
        self.cur = None
        
    def __enter__(self):
        try:
            db_url = os.environ.get('DATABASE_URL', "postgresql://localhost/anapath")
            self.conn = ConnectionPool.get_connection(db_url)
            self.cur = self.conn.cursor()
            return self.cur
        except Exception as e:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.cur:
                self.cur.close()
            # Ne pas fermer la connexion, la garder dans le pool
        except:
            pass

# ================================================
# FONCTIONS UTILITAIRES OPTIMISÉES
# ================================================
def format_date(date_str):
    """Formate une date rapidement"""
    if not date_str:
        return "-"
    try:
        # Méthode plus rapide que strptime
        parts = str(date_str).split('-')
        if len(parts) >= 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return str(date_str)
    except:
        return str(date_str)

def format_sexe(sexe_code):
    """Formate le sexe avec lookup table"""
    sexe_map = {'M': 'Masculin', 'F': 'Féminin'}
    return sexe_map.get(sexe_code, '-')

# ================================================
# MIDDLEWARE POUR GESTION DE MÉMOIRE
# ================================================
@app.after_request
def cleanup(response):
    """Nettoyage mémoire après chaque requête"""
    gc.collect()  # Force le garbage collection
    return response

# ================================================
# GESTION GLOBALE DES ERREURS
# ================================================
@app.errorhandler(Exception)
def handle_error(e):
    """Gestion centralisée des erreurs avec log léger"""
    error_msg = str(e)
    print(f"❌ ERREUR: {error_msg[:200]}")  # Limite la longueur du log
    return jsonify({
        'erreur': error_msg,
        'type': type(e).__name__
    }), 500

# ================================================
# ROUTES DE BASE
# ================================================
@app.route('/', methods=['GET'])
def home():
    """Endpoint racine léger"""
    return jsonify({
        'service': 'ANAPATH API',
        'version': '1.0.0',
        'status': 'operational',
        'memory': f"{gc.mem_free() / 1024 / 1024:.1f}MB libre"
    })

@app.route('/test-db', methods=['GET'])
def test_db():
    """Test DB minimal"""
    try:
        with DBCursor() as cur:
            cur.execute('SELECT 1 as test')
            result = cur.fetchone()
        return jsonify({'status': 'success', 'test': result['test']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ================================================
# UTILISATEURS - OPTIMISÉ
# ================================================
@app.route('/liste_utilisateurs', methods=['GET'])
def liste_utilisateurs():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            cur.execute(
                'SELECT numero, nom, statut FROM utilisateurs WHERE user_id = %s ORDER BY numero',
                (user_id,)
            )
            users = cur.fetchall()
            return jsonify(users)
    except Exception as e:
        print(f"❌ Erreur liste_utilisateurs: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/ajouter_utilisateur', methods=['POST'])
def ajouter_utilisateur():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    try:
        with DBCursor() as cur:
            cur.execute("SELECT nextval('utilisateurs_id_seq') as next_id")
            next_id = cur.fetchone()['next_id']
            
            cur.execute('''
                INSERT INTO utilisateurs (id, user_id, numero, nom, password, statut)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, numero, nom, statut
            ''', (
                next_id, user_id, next_id,
                data['nom'], data['password2'],
                data.get('statut', 'utilisateur')
            ))
            
            new_user = cur.fetchone()
            cur.connection.commit()
            return jsonify(new_user), 201
    except Exception as e:
        print(f"❌ Erreur ajouter_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/valider_utilisateur', methods=['POST'])
def valider_utilisateur():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    if not data or 'nom' not in data or 'password2' not in data:
        return jsonify({'erreur': 'Nom et mot de passe obligatoires'}), 400
    
    try:
        with DBCursor() as cur:
            cur.execute('''
                SELECT numero, nom, statut
                FROM utilisateurs
                WHERE user_id = %s AND nom = %s AND password = %s
            ''', (user_id, data['nom'], data['password2']))
            
            user = cur.fetchone()
            if not user:
                return jsonify({'erreur': 'Identifiants invalides'}), 401
            
            return jsonify({'utilisateur': user})
    except Exception as e:
        print(f"❌ Erreur valider_utilisateur: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# PATIENTS - OPTIMISÉ
# ================================================
@app.route('/patients', methods=['GET', 'POST'])
def patients():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'GET':
                cur.execute('''
                    SELECT id, nom, age, sexe, telephone, adresse
                    FROM patients
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1000
                ''', (user_id,))
                return jsonify(cur.fetchall())
            
            elif request.method == 'POST':
                data = request.json
                if not data or 'nom' not in data:
                    return jsonify({'erreur': 'Nom obligatoire'}), 400
                
                cur.execute('''
                    INSERT INTO patients (user_id, nom, age, sexe, telephone, adresse)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, nom, age, sexe, telephone, adresse
                ''', (
                    user_id, data['nom'], data.get('age'),
                    data.get('sexe'), data.get('telephone'),
                    data.get('adresse')
                ))
                
                new_patient = cur.fetchone()
                cur.connection.commit()
                return jsonify(new_patient), 201
    except Exception as e:
        print(f"❌ Erreur patients: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/patients/<int:id>', methods=['PUT', 'DELETE'])
def patient_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'PUT':
                data = request.json
                if not data or 'nom' not in data:
                    return jsonify({'erreur': 'Nom obligatoire'}), 400
                
                cur.execute('''
                    UPDATE patients
                    SET nom = %s, age = %s, sexe = %s, 
                        telephone = %s, adresse = %s
                    WHERE user_id = %s AND id = %s
                ''', (
                    data['nom'], data.get('age'), data.get('sexe'),
                    data.get('telephone'), data.get('adresse'),
                    user_id, id
                ))
                cur.connection.commit()
                return jsonify({'message': 'Patient modifié'})
            
            elif request.method == 'DELETE':
                cur.execute('DELETE FROM patients WHERE user_id = %s AND id = %s', (user_id, id))
                cur.connection.commit()
                return jsonify({'message': 'Patient supprimé'})
    except Exception as e:
        print(f"❌ Erreur patient_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# MÉDECINS - OPTIMISÉ
# ================================================
@app.route('/medecins', methods=['GET', 'POST'])
def medecins():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'GET':
                cur.execute('''
                    SELECT id, nom, specialite, service, telephone
                    FROM medecins
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1000
                ''', (user_id,))
                return jsonify(cur.fetchall())
            
            elif request.method == 'POST':
                data = request.json
                if not data or 'nom' not in data:
                    return jsonify({'erreur': 'Nom obligatoire'}), 400
                
                cur.execute('''
                    INSERT INTO medecins (user_id, nom, specialite, service, telephone)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, nom, specialite, service, telephone
                ''', (
                    user_id, data['nom'], data.get('specialite'),
                    data.get('service'), data.get('telephone')
                ))
                
                new_medecin = cur.fetchone()
                cur.connection.commit()
                return jsonify(new_medecin), 201
    except Exception as e:
        print(f"❌ Erreur medecins: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/medecins/<int:id>', methods=['PUT', 'DELETE'])
def medecin_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'PUT':
                data = request.json
                if not data or 'nom' not in data:
                    return jsonify({'erreur': 'Nom obligatoire'}), 400
                
                cur.execute('''
                    UPDATE medecins
                    SET nom = %s, specialite = %s, service = %s, telephone = %s
                    WHERE user_id = %s AND id = %s
                ''', (
                    data['nom'], data.get('specialite'),
                    data.get('service'), data.get('telephone'),
                    user_id, id
                ))
                cur.connection.commit()
                return jsonify({'message': 'Médecin modifié'})
            
            elif request.method == 'DELETE':
                cur.execute('DELETE FROM medecins WHERE user_id = %s AND id = %s', (user_id, id))
                cur.connection.commit()
                return jsonify({'message': 'Médecin supprimé'})
    except Exception as e:
        print(f"❌ Erreur medecin_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# COMPTES RENDUS - OPTIMISÉ
# ================================================
@app.route('/comptes-rendus', methods=['GET', 'POST'])
def comptes_rendus():
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'GET':
                # Requête optimisée avec champs spécifiques seulement
                cur.execute('''
                    SELECT 
                        cr.id, cr.numero_enregistrement, cr.date_compte_rendu,
                        cr.statut, cr.created_at,
                        p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                        m.nom as medecin_nom,
                        u.nom as utilisateur_nom
                    FROM comptes_rendus cr
                    LEFT JOIN patients p ON cr.patient_id = p.id
                    LEFT JOIN medecins m ON cr.medecin_id = m.id
                    LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero 
                        AND cr.user_id = u.user_id
                    WHERE cr.user_id = %s
                    ORDER BY cr.id DESC
                    LIMIT 500
                ''', (user_id,))
                reports = cur.fetchall()
                
                # Formatage minimal côté serveur
                for report in reports:
                    if 'date_compte_rendu' in report:
                        report['date_compte_rendu'] = format_date(report['date_compte_rendu'])
                
                return jsonify(reports)
            
            elif request.method == 'POST':
                data = request.json
                required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 
                          'patient_id', 'nature_prelevement', 'date_prelevement']
                
                if not data or any(k not in data for k in required):
                    return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
                
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
                    user_id, utilisateur_id,
                    data['numero_enregistrement'], data['date_compte_rendu'],
                    data['medecin_id'], data.get('service_hospitalier'),
                    data['patient_id'], data['nature_prelevement'],
                    data['date_prelevement'], data.get('renseignements_cliniques'),
                    data.get('macroscopie'), data.get('microscopie'),
                    data.get('conclusion'), data.get('statut', 'en_cours')
                ))
                
                new_report = cur.fetchone()
                cur.connection.commit()
                return jsonify(new_report), 201
    except Exception as e:
        print(f"❌ Erreur comptes_rendus: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

@app.route('/comptes-rendus/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def compte_rendu_detail(id):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        with DBCursor() as cur:
            if request.method == 'GET':
                cur.execute('''
                    SELECT cr.*,
                           p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                           m.nom as medecin_nom,
                           u.nom as utilisateur_nom
                    FROM comptes_rendus cr
                    LEFT JOIN patients p ON cr.patient_id = p.id
                    LEFT JOIN medecins m ON cr.medecin_id = m.id
                    LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero 
                        AND cr.user_id = u.user_id
                    WHERE cr.user_id = %s AND cr.id = %s
                ''', (user_id, id))
                
                report = cur.fetchone()
                if not report:
                    return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
                
                return jsonify(report)
            
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
                    data['numero_enregistrement'], data['date_compte_rendu'],
                    data['medecin_id'], data.get('service_hospitalier'),
                    data['patient_id'], data['nature_prelevement'],
                    data['date_prelevement'], data.get('renseignements_cliniques'),
                    data.get('macroscopie'), data.get('microscopie'),
                    data.get('conclusion'), data.get('statut'),
                    user_id, id
                ))
                cur.connection.commit()
                return jsonify({'message': 'Compte rendu modifié'})
            
            elif request.method == 'DELETE':
                cur.execute('DELETE FROM comptes_rendus WHERE user_id = %s AND id = %s', 
                          (user_id, id))
                cur.connection.commit()
                return jsonify({'message': 'Compte rendu supprimé'})
    except Exception as e:
        print(f"❌ Erreur compte_rendu_detail: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# PDF GENERATION - LAZY LOADING
# ================================================
@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
    """Génération PDF avec lazy loading des modules lourds"""
    user_id = request.headers.get('X-User-ID') or request.args.get('user_id')
    
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    # Import différé pour économiser la mémoire
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from io import BytesIO
    except ImportError as e:
        return jsonify({'erreur': f'Module ReportLab manquant: {str(e)}'}), 500
    
    try:
        with DBCursor() as cur:
            cur.execute('''
                SELECT cr.*,
                       p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                       m.nom as medecin_nom, m.specialite as medecin_specialite,
                       u.nom as utilisateur_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                LEFT JOIN utilisateurs u ON cr.utilisateur_id = u.numero 
                    AND cr.user_id = u.user_id
                WHERE cr.user_id = %s AND cr.id = %s
            ''', (user_id, id))
            
            report = cur.fetchone()
            
            if not report:
                return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
            
            # Générer le PDF en mémoire
            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=A4,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40
            )
            
            story = []
            styles = getSampleStyleSheet()
            
            # Styles minimalistes
            entete_style = ParagraphStyle(
                'Entete', parent=styles['Normal'],
                fontName='Helvetica-Bold', fontSize=14,
                alignment=1, spaceAfter=4
            )
            
            info_style = ParagraphStyle(
                'Info', parent=styles['Normal'],
                fontName='Helvetica', fontSize=10,
                leading=12
            )
            
            label_style = ParagraphStyle(
                'Label', parent=styles['Normal'],
                fontName='Helvetica-Bold', fontSize=9,
                leading=12
            )
            
            # Construction du PDF (version simplifiée)
            story.append(Paragraph("ANAPATH ELYOUSR", entete_style))
            story.append(Paragraph("LABORATOIRE D'ANATOMIE & DE CYTOLOGIE PATHOLOGIQUES", 
                                 entete_style))
            story.append(Spacer(1, 20))
            
            # Tableau d'informations
            info_data = [
                ["N d'enregistrement:", report['numero_enregistrement'], 
                 "Médecin:", report['medecin_nom'] or '-'],
                ["Date CR:", format_date(report['date_compte_rendu']),
                 "Service:", report.get('service_hospitalier', '-')],
                ["Patient:", report['patient_nom'] or '-',
                 "Âge:", str(report['patient_age'] or '-'),
                 "Sexe:", format_sexe(report['patient_sexe'])],
                ["Nature prélèvement:", report['nature_prelevement'] or '-',
                 "Date prélèvement:", format_date(report['date_prelevement'])]
            ]
            
            table = Table(info_data, colWidths=[4*cm, 6*cm, 2.5*cm, 5*cm])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            story.append(table)
            
            # Sections principales
            sections = [
                ('Renseignements Cliniques', report.get('renseignements_cliniques')),
                ('Macroscopie', report.get('macroscopie')),
                ('Microscopie', report.get('microscopie')),
                ('Conclusion', report.get('conclusion'))
            ]
            
            for title, content in sections:
                if content and str(content).strip():
                    story.append(Spacer(1, 10))
                    story.append(Paragraph(f"<b>{title}:</b>", label_style))
                    
                    # Formater le contenu avec sauts de ligne
                    text_lines = str(content).strip().split('\n')
                    for line in text_lines:
                        if line.strip():
                            story.append(Paragraph(line.strip(), info_style))
            
            # Signature
            story.append(Spacer(1, 30))
            signature = Paragraph(
                "<b>Confraternellement</b><br/>Dr. BENFOULA Amel",
                ParagraphStyle(
                    'Signature', parent=styles['Normal'],
                    fontName='Helvetica', fontSize=10,
                    alignment=2, spaceBefore=20
                )
            )
            story.append(signature)
            
            # Générer le PDF
            doc.build(story)
            buffer.seek(0)
            
            # Nettoyage mémoire
            del story, doc, styles
            gc.collect()
            
            nom_fichier = f"CR_{report['numero_enregistrement']}.pdf"
            return send_file(
                buffer,
                as_attachment=True,
                download_name=nom_fichier,
                mimetype='application/pdf'
            )
            
    except Exception as e:
        print(f"❌ ERREUR PDF CR {id}: {str(e)}")
        return jsonify({'erreur': f'Erreur génération PDF: {str(e)}'}), 500

# ================================================
# TEMPLATES - OPTIMISÉ
# ================================================
@app.route('/api/templates', methods=['GET'])
def get_templates():
    user_id = request.headers.get('X-User-ID')
    try:
        with DBCursor() as cur:
            cur.execute("""
                SELECT id, code, titre, organe, tags
                FROM templates 
                WHERE user_id = %s OR user_id = 'system'
                ORDER BY titre
                LIMIT 200
            """, (user_id,))
            return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500

@app.route('/api/templates/<int:id>', methods=['GET'])
def get_template_by_id(id):
    user_id = request.headers.get('X-User-ID')
    try:
        with DBCursor() as cur:
            cur.execute("""
                SELECT * FROM templates 
                WHERE id = %s AND (user_id = %s OR user_id = 'system')
            """, (id, user_id))
            
            template = cur.fetchone()
            if not template:
                return jsonify({'erreur': 'Template non trouvé'}), 404
            return jsonify(template)
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500

@app.route('/api/templates', methods=['POST'])
def create_template():
    user_id = request.headers.get('X-User-ID')
    data = request.json
    
    if not data.get('code') or not data.get('titre'):
        return jsonify({'erreur': 'Code et titre requis'}), 400
    
    try:
        with DBCursor() as cur:
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
            cur.connection.commit()
            return jsonify({'success': True, 'id': new_id}), 201
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500

@app.route('/api/templates/<int:id>', methods=['PUT'])
def update_template(id):
    user_id = request.headers.get('X-User-ID')
    data = request.json
    
    try:
        with DBCursor() as cur:
            cur.execute("""
                UPDATE templates SET
                    code = COALESCE(%s, code),
                    titre = COALESCE(%s, titre),
                    organe = %s,
                    tags = %s,
                    renseignements_cliniques = %s,
                    macroscopie = %s,
                    microscopie = %s,
                    conclusion = %s
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
                return jsonify({'erreur': 'Template non trouvé'}), 404
            
            cur.connection.commit()
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500

@app.route('/api/templates/<int:id>', methods=['DELETE'])
def delete_template(id):
    user_id = request.headers.get('X-User-ID')
    
    try:
        with DBCursor() as cur:
            cur.execute("""
                DELETE FROM templates 
                WHERE id = %s AND (user_id = %s OR user_id = 'system')
                RETURNING id
            """, (id, user_id))
            
            if not cur.fetchone():
                return jsonify({'erreur': 'Template non trouvé'}), 404
            
            cur.connection.commit()
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500

# ================================================
# SHUTDOWN HOOK
# ================================================
@app.teardown_appcontext
def cleanup_pool(exception=None):
    """Nettoie le pool de connexions à l'arrêt"""
    ConnectionPool.close_all()
    gc.collect()

# ================================================
# DÉMARRAGE OPTIMISÉ
# ================================================
if __name__ == '__main__':
    print("🚀 Démarrage ANAPATH API optimisé...")
    print(f"📊 Mémoire initiale: {gc.mem_free() / 1024 / 1024:.1f}MB libre")
    
    # Configuration pour économiser la RAM
    import sys
    if sys.platform != 'win32':
        import resource
        # Limite la mémoire si nécessaire (décommenter si besoin)
        # resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    
    app.run(
        debug=False,  # Désactiver debug en production
        host='0.0.0.0', 
        port=int(os.environ.get('PORT', 5000)),
        threaded=True,
        processes=1  # Utiliser un seul processus pour économiser la RAM
    )
