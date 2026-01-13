from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
import gc
import traceback

# Configuration minimale
app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://hicham558.github.io", "http://localhost:*"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-User-ID", "Authorization"]
}})

# ================================================
# CONFIGURATION POUR RENDER.COM
# ================================================
def get_db():
    """Obtient une connexion à la base de données"""
    try:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            # Mode développement local
            db_url = "postgresql://localhost/anapath"
        
        # Connexion avec timeout court
        conn = psycopg2.connect(
            db_url,
            cursor_factory=RealDictCursor,
            connect_timeout=5,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=2
        )
        return conn
    except Exception as e:
        print(f"❌ ERREUR CONNEXION DB: {str(e)}")
        raise

# ================================================
# FONCTIONS UTILITAIRES
# ================================================
def format_date(date_str):
    """Formate une date rapidement"""
    if not date_str:
        return "-"
    try:
        if isinstance(date_str, datetime):
            return date_str.strftime('%d/%m/%Y')
        parts = str(date_str).split('-')
        if len(parts) >= 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return str(date_str)
    except:
        return str(date_str)

def format_sexe(sexe_code):
    """Formate le sexe"""
    if sexe_code == 'M':
        return 'Masculin'
    elif sexe_code == 'F':
        return 'Féminin'
    return '-'

# ================================================
# GESTION DES ERREURS
# ================================================
@app.errorhandler(Exception)
def handle_error(e):
    """Gestion centralisée des erreurs"""
    error_msg = str(e)
    print(f"❌ ERREUR: {error_msg}")
    return jsonify({
        'erreur': 'Une erreur est survenue',
        'type': type(e).__name__
    }), 500

# ================================================
# ROUTES DE BASE
# ================================================
@app.route('/', methods=['GET'])
def home():
    """Endpoint racine"""
    return jsonify({
        'service': 'ANAPATH API',
        'version': '2.0.0',
        'status': 'operational'
    })

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de santé pour Render"""
    return jsonify({'status': 'healthy'}), 200

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
        return jsonify(users)
    except Exception as e:
        print(f"❌ Erreur liste_utilisateurs: {str(e)}")
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
        conn.commit()
        return jsonify(new_user), 201
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
                SELECT id, nom, age, sexe, telephone, adresse
                FROM patients
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 500
            ''', (user_id,))
            patients_list = cur.fetchall()
            return jsonify(patients_list)
        
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
            return jsonify(new_patient), 201
    
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
                SELECT id, nom, specialite, service, telephone
                FROM medecins
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 500
            ''', (user_id,))
            medecins_list = cur.fetchall()
            return jsonify(medecins_list)
        
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
            return jsonify(new_medecin), 201
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur medecins: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ================================================
# COMPTES RENDUS - VERSION SIMPLIFIÉE
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
            # Requête très simple pour économiser la mémoire
            cur.execute('''
                SELECT 
                    cr.id, cr.numero_enregistrement, cr.date_compte_rendu,
                    cr.statut, cr.created_at,
                    p.nom as patient_nom,
                    m.nom as medecin_nom
                FROM comptes_rendus cr
                LEFT JOIN patients p ON cr.patient_id = p.id
                LEFT JOIN medecins m ON cr.medecin_id = m.id
                WHERE cr.user_id = %s
                ORDER BY cr.id DESC
                LIMIT 100
            ''', (user_id,))
            reports = cur.fetchall()
            
            # Formatage simple
            for report in reports:
                if report.get('date_compte_rendu'):
                    report['date_compte_rendu'] = format_date(report['date_compte_rendu'])
            
            return jsonify(reports)
        
        elif request.method == 'POST':
            data = request.json
            required = ['numero_enregistrement', 'date_compte_rendu', 'medecin_id', 
                       'patient_id', 'nature_prelevement']
            
            if not data or any(k not in data for k in required):
                return jsonify({'erreur': 'Champs obligatoires manquants'}), 400
            
            cur.execute('''
                INSERT INTO comptes_rendus (
                    user_id, numero_enregistrement, date_compte_rendu,
                    medecin_id, patient_id, nature_prelevement,
                    date_prelevement, renseignements_cliniques,
                    macroscopie, microscopie, conclusion, statut
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                data['numero_enregistrement'],
                data['date_compte_rendu'],
                data['medecin_id'],
                data['patient_id'],
                data['nature_prelevement'],
                data.get('date_prelevement'),
                data.get('renseignements_cliniques', ''),
                data.get('macroscopie', ''),
                data.get('microscopie', ''),
                data.get('conclusion', ''),
                data.get('statut', 'en_cours')
            ))
            
            new_report = cur.fetchone()
            conn.commit()
            return jsonify({'id': new_report['id']}), 201
    
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

# ================================================
# PDF GENERATION - VERSION ULTRA SIMPLE
# ================================================
@app.route('/comptes-rendus/<int:id>/print', methods=['GET'])
def print_compte_rendu(id):
    """Génération PDF simplifiée"""
    user_id = request.headers.get('X-User-ID') or request.args.get('user_id')
    
    if not user_id:
        return jsonify({'erreur': 'Identifiant manquant'}), 401
    
    # Import différé
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from io import BytesIO
    except ImportError as e:
        return jsonify({'erreur': 'Module PDF non disponible'}), 500
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Requête minimale
        cur.execute('''
            SELECT cr.numero_enregistrement, cr.date_compte_rendu,
                   p.nom as patient_nom, p.age as patient_age, p.sexe as patient_sexe,
                   m.nom as medecin_nom,
                   cr.nature_prelevement, cr.date_prelevement,
                   cr.renseignements_cliniques, cr.macroscopie,
                   cr.microscopie, cr.conclusion
            FROM comptes_rendus cr
            LEFT JOIN patients p ON cr.patient_id = p.id
            LEFT JOIN medecins m ON cr.medecin_id = m.id
            WHERE cr.user_id = %s AND cr.id = %s
        ''', (user_id, id))
        
        report = cur.fetchone()
        
        if not report:
            return jsonify({'erreur': 'Compte rendu non trouvé'}), 404
        
        # Création PDF simple
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # En-tête
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width/2, height-50, "ANAPATH ELYOUSR")
        c.setFont("Helvetica", 10)
        c.drawCentredString(width/2, height-70, "Laboratoire d'Anatomie et Cytologie Pathologiques")
        
        # Informations de base
        y = height - 100
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"N° Enregistrement: {report['numero_enregistrement']}")
        c.drawString(width/2, y, f"Date: {format_date(report['date_compte_rendu'])}")
        
        y -= 20
        c.drawString(50, y, f"Patient: {report['patient_nom'] or '-'}")
        c.drawString(width/2, y, f"Âge: {report['patient_age'] or '-'} | Sexe: {format_sexe(report['patient_sexe'])}")
        
        y -= 20
        c.drawString(50, y, f"Médecin: {report['medecin_nom'] or '-'}")
        
        y -= 20
        c.drawString(50, y, f"Nature prélèvement: {report['nature_prelevement']}")
        c.drawString(width/2, y, f"Date prélèvement: {format_date(report['date_prelevement'])}")
        
        # Sections
        sections = [
            ('RENSEIGNEMENTS CLINIQUES', report.get('renseignements_cliniques')),
            ('MACROSCOPIE', report.get('macroscopie')),
            ('MICROSCOPIE', report.get('microscopie')),
            ('CONCLUSION', report.get('conclusion'))
        ]
        
        y -= 40
        for title, content in sections:
            if content and str(content).strip():
                c.setFont("Helvetica-Bold", 11)
                c.drawString(50, y, title + ":")
                y -= 15
                
                c.setFont("Helvetica", 10)
                text = str(content).strip()
                # Découpage simple
                lines = []
                for line in text.split('\n'):
                    if len(line) > 100:
                        # Découpe les lignes trop longues
                        while len(line) > 100:
                            lines.append(line[:100])
                            line = line[100:]
                        lines.append(line)
                    else:
                        lines.append(line)
                
                for line in lines:
                    if y < 50:  # Nouvelle page si nécessaire
                        c.showPage()
                        y = height - 50
                        c.setFont("Helvetica", 10)
                    c.drawString(60, y, line.strip())
                    y -= 14
                y -= 10
        
        # Signature
        if y < 100:
            c.showPage()
            y = height - 50
        
        c.setFont("Helvetica", 10)
        c.drawRightString(width-50, y, "Confraternellement")
        c.drawRightString(width-50, y-15, "Dr. BENFOULA Amel")
        
        c.save()
        buffer.seek(0)
        
        # Nettoyage mémoire
        del c
        gc.collect()
        
        nom_fichier = f"CR_{report['numero_enregistrement']}.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=nom_fichier,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"❌ ERREUR PDF: {str(e)}")
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
    print("🚀 Démarrage ANAPATH API pour Render.com...")
    print(f"📍 Port: {os.environ.get('PORT', 5000)}")
    
    port = int(os.environ.get('PORT', 5000))
    
    # Désactive le mode debug pour production
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        threaded=True
    )
