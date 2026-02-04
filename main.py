from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os
from io import BytesIO
import traceback
import textwrap
import tempfile
import shutil
from werkzeug.utils import secure_filename
from flask import Response, stream_with_context
import subprocess
import base64
from urllib.parse import urlparse


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
    DATABASE_URL = os.environ['DATABASE_NEON']
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

def generer_numero_recu(user_id, type_examen):
    """
    Génère un numéro de reçu automatique selon le format:
    XXXTYYMM où:
    - XXX = numéro séquentiel sur 3 chiffres
    - T = type d'examen (H=Histologie, B=Biopsie, C=Cytologie, F=FCV, I=Immuno-Histochimie)
    - YY = année sur 2 chiffres (26 pour 2026)
    - MM = mois en lettre (A=Jan, B=Fév, C=Mar, etc.)
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Date actuelle
        maintenant = datetime.now()
        annee = maintenant.year % 100  # 2026 -> 26
        mois = maintenant.month
        
        # Correspondance type d'examen -> lettre
        type_lettres = {
            'histologie': 'H',
            'biopsie': 'B',
            'cytologie': 'C',
            'fcv': 'F',
            'immuno-histochimie': 'I',
            'consultation': 'H',  # Par défaut
            'examen': 'H',
            'analyse': 'H',
            'autre': 'H'
        }
        
        # Correspondance mois -> lettre
        mois_lettres = {
            1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E', 6: 'F',
            7: 'G', 8: 'H', 9: 'I', 10: 'J', 11: 'K', 12: 'L'
        }
        
        type_lettre = type_lettres.get(type_examen.lower(), 'H')
        mois_lettre = mois_lettres[mois]
        
        print(f"🔍 Génération reçu pour: user={user_id}, type={type_examen}, année={annee}, mois={mois}")
        
        # ✅ Vérifier d'abord si le compteur existe
        cur.execute('''
            SELECT compteur FROM compteurs_recus
            WHERE user_id = %s AND type_examen = %s AND annee = %s AND mois = %s
        ''', (user_id, type_examen.lower(), annee, mois))
        
        existing = cur.fetchone()
        
        if existing:
            # Incrémenter le compteur existant
            compteur = existing['compteur'] + 1
            cur.execute('''
                UPDATE compteurs_recus 
                SET compteur = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND type_examen = %s AND annee = %s AND mois = %s
            ''', (compteur, user_id, type_examen.lower(), annee, mois))
        else:
            # Créer un nouveau compteur
            compteur = 1
            cur.execute('''
                INSERT INTO compteurs_recus (user_id, type_examen, annee, mois, compteur)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, type_examen.lower(), annee, mois, compteur))
        
        # Formater le numéro: 001H26A
        numero_recu = f"{compteur:03d}{type_lettre}{annee:02d}{mois_lettre}"
        
        conn.commit()
        
        print(f"✅ Numéro généré: {numero_recu} (compteur={compteur})")
        
        return numero_recu
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur génération numéro reçu: {str(e)}")
        traceback.print_exc()
        # En cas d'erreur, retourner un numéro temporaire
        temp_num = f"TMP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        print(f"⚠️ Utilisation numéro temporaire: {temp_num}")
        return temp_num
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
@app.route('/compteurs-recus', methods=['GET'])
def voir_compteurs():
    """Endpoint pour consulter les compteurs de numéros de reçu"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT 
                type_examen,
                annee,
                mois,
                compteur,
                updated_at
            FROM compteurs_recus
            WHERE user_id = %s
            ORDER BY annee DESC, mois DESC, type_examen
        ''', (user_id,))
        
        compteurs = cur.fetchall()
        
        # Formater les résultats
        result = []
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        
        for c in compteurs:
            result.append({
                'type_examen': c['type_examen'],
                'periode': f"{mois_noms[c['mois']]} 20{c['annee']}",
                'compteur': c['compteur'],
                'derniere_utilisation': c['updated_at'].strftime('%d/%m/%Y %H:%M') if c['updated_at'] else None
            })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur compteurs: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
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
# BACKUP & RESTORE DATABASE - SANS TABLE
# ================================================


@app.route('/api/database/backup', methods=['POST'])
def backup_database():
    """Crée une sauvegarde complète de la base de données et la retourne directement"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        # Parser l'URL de la base de données
        url = urlparse(DATABASE_URL)
        
        # Nom du fichier backup
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"anapath_backup_{user_id}_{timestamp}.sql"
        
        # Commande pg_dump pour extraire uniquement les données de l'utilisateur
        dump_command = [
            'pg_dump',
            '--host', url.hostname,
            '--port', str(url.port or 5432),
            '--username', url.username,
            '--dbname', url.path[1:],
            '--no-password',
            '--format', 'plain',
            '--data-only',  # Seulement les données, pas la structure
            '--no-owner',
            '--no-privileges',
            '--inserts',  # Format INSERT au lieu de COPY
        ]
        
        # Variables d'environnement pour le mot de passe
        env = os.environ.copy()
        if url.password:
            env['PGPASSWORD'] = url.password
        
        # Exécuter pg_dump
        result = subprocess.run(
            dump_command,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )
        
        if result.returncode != 0:
            print(f"❌ Erreur pg_dump: {result.stderr}")
            return jsonify({'erreur': f'Erreur backup: {result.stderr}'}), 500
        
        sql_content = result.stdout
        
        # Filtrer uniquement les données de l'utilisateur
        filtered_sql = filter_user_data(sql_content, user_id)
        
        # Encoder en base64
        sql_base64 = base64.b64encode(filtered_sql.encode('utf-8')).decode('utf-8')
        
        return jsonify({
            'success': True,
            'filename': backup_filename,
            'size': len(filtered_sql.encode('utf-8')),
            'created_at': datetime.now().isoformat(),
            'sql_base64': sql_base64
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({'erreur': 'Timeout - la sauvegarde a pris trop de temps'}), 500
    except Exception as e:
        print(f"❌ Erreur backup_database: {str(e)}")
        traceback.print_exc()
        return jsonify({'erreur': str(e)}), 500


def filter_user_data(sql_content, user_id):
    """
    Filtre le SQL pour ne garder que les données de l'utilisateur
    (Cette fonction peut être adaptée selon vos besoins)
    """
    lines = sql_content.split('\n')
    filtered_lines = []
    
    for line in lines:
        # Garder seulement les INSERT qui contiennent le user_id
        if line.strip().startswith('INSERT'):
            if f"'{user_id}'" in line or f'"{user_id}"' in line:
                filtered_lines.append(line)
        # Garder aussi les commentaires et SET
        elif line.strip().startswith('--') or line.strip().startswith('SET'):
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)


@app.route('/api/database/restore', methods=['POST'])
def restore_database():
    """Restaure une base de données depuis un fichier SQL uploadé"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        # Récupérer le fichier SQL depuis le body
        data = request.json
        
        if not data or 'sql_content' not in data:
            return jsonify({'erreur': 'Contenu SQL manquant'}), 400
        
        # Décoder le base64
        try:
            sql_content = base64.b64decode(data['sql_content']).decode('utf-8')
        except:
            # Si ce n'est pas du base64, utiliser tel quel
            sql_content = data['sql_content']
        
        # Vérifier que le SQL contient bien des données de cet utilisateur
        if user_id not in sql_content:
            return jsonify({'erreur': 'Cette sauvegarde ne contient pas vos données'}), 400
        
        # Parser l'URL de la base de données
        url = urlparse(DATABASE_URL)
        
        # Créer un fichier temporaire avec le SQL
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as tmp:
            tmp.write(sql_content)
            tmp_path = tmp.name
        
        try:
            # Variables d'environnement
            env = os.environ.copy()
            if url.password:
                env['PGPASSWORD'] = url.password
            
            # IMPORTANT: Supprimer d'abord les données existantes de l'utilisateur
            conn = get_db()
            cur = conn.cursor()
            
            # Lister toutes les tables à nettoyer
            tables_to_clean = [
                'comptes_rendus',
                'paiements',
                'patients',
                'medecins',
                'utilisateurs',
                'fichiers_paiements',
                'compteurs_recus'
            ]
            
            for table in tables_to_clean:
                try:
                    cur.execute(f'DELETE FROM {table} WHERE user_id = %s', (user_id,))
                except Exception as e:
                    print(f"⚠️ Erreur nettoyage {table}: {str(e)}")
            
            conn.commit()
            cur.close()
            conn.close()
            
            # Commande psql pour exécuter le SQL
            restore_command = [
                'psql',
                '--host', url.hostname,
                '--port', str(url.port or 5432),
                '--username', url.username,
                '--dbname', url.path[1:],
                '--file', tmp_path,
                '--quiet'
            ]
            
            # Exécuter psql
            result = subprocess.run(
                restore_command,
                env=env,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                print(f"❌ Erreur psql: {result.stderr}")
                return jsonify({'erreur': f'Erreur restauration: {result.stderr}'}), 500
            
            return jsonify({
                'success': True,
                'message': 'Base de données restaurée avec succès',
                'restored_at': datetime.now().isoformat()
            })
            
        finally:
            # Supprimer le fichier temporaire
            try:
                os.unlink(tmp_path)
            except:
                pass
        
    except subprocess.TimeoutExpired:
        return jsonify({'erreur': 'Timeout - la restauration a pris trop de temps'}), 500
    except Exception as e:
        print(f"❌ Erreur restore_database: {str(e)}")
        traceback.print_exc()
        return jsonify({'erreur': str(e)}), 500


@app.route('/api/database/backup-structure', methods=['POST'])
def backup_structure():
    """Sauvegarde uniquement la structure de la base (pour migration)"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        url = urlparse(DATABASE_URL)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # pg_dump avec --schema-only
        dump_command = [
            'pg_dump',
            '--host', url.hostname,
            '--port', str(url.port or 5432),
            '--username', url.username,
            '--dbname', url.path[1:],
            '--no-password',
            '--schema-only',  # Seulement la structure
            '--no-owner',
            '--no-privileges'
        ]
        
        env = os.environ.copy()
        if url.password:
            env['PGPASSWORD'] = url.password
        
        result = subprocess.run(
            dump_command,
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            return jsonify({'erreur': f'Erreur: {result.stderr}'}), 500
        
        sql_base64 = base64.b64encode(result.stdout.encode('utf-8')).decode('utf-8')
        
        return jsonify({
            'success': True,
            'filename': f'anapath_structure_{timestamp}.sql',
            'sql_base64': sql_base64
        })
        
    except Exception as e:
        print(f"❌ Erreur backup_structure: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# ================================================
# GESTION DES FICHIERS ATTACHES - POSTGRESQL
# ================================================
@app.route('/api/paiements/<int:paiement_id>/fichiers/chunk', methods=['POST'])
def upload_file_chunk(paiement_id):
    """Upload un fichier volumineux par chunks"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        # Récupérer les paramètres du chunk
        chunk = request.files.get('chunk')
        chunk_index = int(request.form.get('chunkIndex'))
        total_chunks = int(request.form.get('totalChunks'))
        file_name = secure_filename(request.form.get('fileName'))
        file_size = int(request.form.get('fileSize'))
        
        if not chunk or not file_name:
            return jsonify({'erreur': 'Données manquantes'}), 400
        
        # Vérifier que le paiement existe
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT numero_cr FROM paiements WHERE id = %s AND user_id = %s', 
                   (paiement_id, user_id))
        paiement = cur.fetchone()
        
        if not paiement:
            return jsonify({'erreur': 'Paiement non trouvé'}), 404
        
        numero_cr = paiement['numero_cr']
        
        # Créer un dossier temporaire pour les chunks
        temp_base = tempfile.gettempdir()
        upload_folder = os.path.join(temp_base, 'anapath_uploads', str(user_id), str(paiement_id))
        os.makedirs(upload_folder, exist_ok=True)
        
        # Créer un sous-dossier pour ce fichier spécifique
        file_folder = os.path.join(upload_folder, file_name)
        os.makedirs(file_folder, exist_ok=True)
        
        # Sauvegarder le chunk
        chunk_path = os.path.join(file_folder, f"chunk_{chunk_index}")
        chunk.save(chunk_path)
        
        # Si c'est le dernier chunk, assembler le fichier
        if chunk_index == total_chunks - 1:
            final_file_path = os.path.join(file_folder, file_name)
            
            # Assembler tous les chunks
            with open(final_file_path, 'wb') as final_file:
                for i in range(total_chunks):
                    chunk_file = os.path.join(file_folder, f"chunk_{i}")
                    
                    if not os.path.exists(chunk_file):
                        raise Exception(f"Chunk {i} manquant")
                    
                    with open(chunk_file, 'rb') as cf:
                        final_file.write(cf.read())
                    
                    # Supprimer le chunk après lecture
                    os.remove(chunk_file)
            
            # Lire le fichier complet
            with open(final_file_path, 'rb') as f:
                donnees = f.read()
            
            # Vérifier la taille (max 50MB)
            if len(donnees) > 50 * 1024 * 1024:
                os.remove(final_file_path)
                shutil.rmtree(file_folder)
                return jsonify({'erreur': 'Fichier trop volumineux (max 50MB)'}), 400
            
            # Détecter le type MIME
            import mimetypes
            mime_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            
            # Enregistrer dans PostgreSQL
            cur.execute('''
                INSERT INTO fichiers_paiements 
                (user_id, paiement_id, numero_cr, nom_original, type_mime, taille_bytes, donnees, uploaded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, nom_original, type_mime, taille_bytes, date_upload
            ''', (user_id, paiement_id, numero_cr, file_name, 
                  mime_type, len(donnees), donnees, user_id))
            
            result = cur.fetchone()
            conn.commit()
            
            # Nettoyer les fichiers temporaires
            os.remove(final_file_path)
            shutil.rmtree(file_folder)
            
            # Nettoyer le dossier parent si vide
            try:
                if not os.listdir(upload_folder):
                    os.rmdir(upload_folder)
            except:
                pass
            
            return jsonify({
                'message': 'Fichier uploadé avec succès',
                'fichier': {
                    'id': result['id'],
                    'nom': result['nom_original'],
                    'type': result['type_mime'],
                    'taille': result['taille_bytes'],
                    'date_upload': result['date_upload'].isoformat() if result['date_upload'] else None
                }
            }), 200
        
        # Si ce n'est pas le dernier chunk, retourner un statut de progression
        return jsonify({
            'message': f'Chunk {chunk_index + 1}/{total_chunks} reçu',
            'progress': round((chunk_index + 1) / total_chunks * 100, 2)
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur upload chunk: {str(e)}")
        
        # Nettoyer en cas d'erreur
        try:
            if 'file_folder' in locals() and os.path.exists(file_folder):
                shutil.rmtree(file_folder)
        except:
            pass
        
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================================
# FONCTION HELPER POUR NETTOYER LES ANCIENS CHUNKS
# ================================================

def cleanup_old_temp_files():
    """Nettoyer les fichiers temporaires de plus de 24h"""
    try:
        temp_base = tempfile.gettempdir()
        upload_folder = os.path.join(temp_base, 'anapath_uploads')
        
        if not os.path.exists(upload_folder):
            return
        
        import time
        current_time = time.time()
        
        for root, dirs, files in os.walk(upload_folder):
            for file in files:
                file_path = os.path.join(root, file)
                file_age = current_time - os.path.getmtime(file_path)
                
                # Supprimer les fichiers de plus de 24h
                if file_age > 24 * 3600:
                    try:
                        os.remove(file_path)
                        print(f"🗑️ Fichier temporaire supprimé: {file_path}")
                    except:
                        pass
        
        # Supprimer les dossiers vides
        for root, dirs, files in os.walk(upload_folder, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except:
                    pass
                    
    except Exception as e:
        print(f"⚠️ Erreur nettoyage temp files: {str(e)}")


# ================================================
# ROUTE POUR VÉRIFIER L'ÉTAT D'UN UPLOAD
# ================================================

@app.route('/api/paiements/<int:paiement_id>/fichiers/upload-status', methods=['GET'])
def check_upload_status(paiement_id):
    """Vérifier l'état d'un upload en cours"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    file_name = request.args.get('fileName')
    if not file_name:
        return jsonify({'erreur': 'fileName manquant'}), 400
    
    try:
        file_name = secure_filename(file_name)
        temp_base = tempfile.gettempdir()
        file_folder = os.path.join(temp_base, 'anapath_uploads', str(user_id), str(paiement_id), file_name)
        
        if not os.path.exists(file_folder):
            return jsonify({'status': 'not_started', 'chunks_received': 0})
        
        # Compter les chunks reçus
        chunks = [f for f in os.listdir(file_folder) if f.startswith('chunk_')]
        
        return jsonify({
            'status': 'in_progress',
            'chunks_received': len(chunks)
        })
        
    except Exception as e:
        print(f"❌ Erreur check status: {str(e)}")
        return jsonify({'erreur': str(e)}), 500


# ================================================
# ROUTE POUR ANNULER UN UPLOAD EN COURS
# ================================================

@app.route('/api/paiements/<int:paiement_id>/fichiers/cancel-upload', methods=['POST'])
def cancel_upload(paiement_id):
    """Annuler un upload en cours et nettoyer les chunks"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    try:
        data = request.get_json()
        file_name = secure_filename(data.get('fileName'))
        
        if not file_name:
            return jsonify({'erreur': 'fileName manquant'}), 400
        
        temp_base = tempfile.gettempdir()
        file_folder = os.path.join(temp_base, 'anapath_uploads', str(user_id), str(paiement_id), file_name)
        
        if os.path.exists(file_folder):
            shutil.rmtree(file_folder)
            return jsonify({'message': 'Upload annulé et chunks supprimés'})
        
        return jsonify({'message': 'Aucun upload en cours pour ce fichier'})
        
    except Exception as e:
        print(f"❌ Erreur cancel upload: {str(e)}")
        return jsonify({'erreur': str(e)}), 500

# 1. Upload de fichiers
@app.route('/api/paiements/<int:paiement_id>/fichiers', methods=['POST'])
def upload_fichier_paiement(paiement_id):
    """Upload un ou plusieurs fichiers pour un paiement"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        # Récupérer le numéro CR pour le dossier
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('SELECT numero_cr FROM paiements WHERE id = %s AND user_id = %s', 
                   (paiement_id, user_id))
        paiement = cur.fetchone()
        
        if not paiement:
            return jsonify({'erreur': 'Paiement non trouvé'}), 404
        
        numero_cr = paiement['numero_cr']
        
        fichiers_enregistres = []
        
        # Traiter chaque fichier
        for file_key in request.files:
            file = request.files[file_key]
            
            if file.filename == '':
                continue
            
            # Lire le fichier en bytes
            donnees = file.read()
            
            # Vérifier la taille (max 10MB)
            if len(donnees) > 10 * 1024 * 1024:
                return jsonify({'erreur': f'Fichier trop volumineux: {file.filename} (max 10MB)'}), 400
            
            # Enregistrer dans PostgreSQL
            cur.execute('''
                INSERT INTO fichiers_paiements 
                (user_id, paiement_id, numero_cr, nom_original, type_mime, taille_bytes, donnees)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, nom_original, type_mime, taille_bytes, date_upload
            ''', (user_id, paiement_id, numero_cr, file.filename, 
                  file.mimetype, len(donnees), donnees))
            
            result = cur.fetchone()
            fichiers_enregistres.append(dict(result))
        
        conn.commit()
        
        return jsonify({
            'message': f'{len(fichiers_enregistres)} fichier(s) enregistré(s)',
            'fichiers': fichiers_enregistres
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur upload fichier: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 2. Lister les fichiers d'un paiement
@app.route('/api/paiements/<int:paiement_id>/fichiers', methods=['GET'])
def get_fichiers_paiement(paiement_id):
    """Récupérer la liste des fichiers attachés à un paiement"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT 
                id, paiement_id, numero_cr, nom_original, 
                type_mime, taille_bytes, date_upload, uploaded_by
            FROM fichiers_paiements 
            WHERE paiement_id = %s AND user_id = %s
            ORDER BY date_upload DESC
        ''', (paiement_id, user_id))
        
        fichiers = cur.fetchall()
        
        result = []
        for fichier in fichiers:
            result.append({
                'id': fichier['id'],
                'paiement_id': fichier['paiement_id'],
                'numero_cr': fichier['numero_cr'],
                'nom': fichier['nom_original'],
                'type': fichier['type_mime'],
                'taille': fichier['taille_bytes'],
                'date_upload': fichier['date_upload'].isoformat() if fichier['date_upload'] else None,
                'uploaded_by': fichier['uploaded_by']
            })
        
        return jsonify({'fichiers': result})
        
    except Exception as e:
        print(f"❌ Erreur get fichiers: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 3. Télécharger un fichier
@app.route('/api/fichiers/<int:fichier_id>/download', methods=['GET'])
def download_fichier(fichier_id):
    """Télécharger un fichier avec streaming optimisé"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # D'abord récupérer les métadonnées SANS les données
        cur.execute('''
            SELECT nom_original, type_mime, taille_bytes
            FROM fichiers_paiements 
            WHERE id = %s AND user_id = %s
        ''', (fichier_id, user_id))
        
        fichier_info = cur.fetchone()
        
        if not fichier_info:
            return jsonify({'erreur': 'Fichier non trouvé'}), 404
        
        nom_fichier = fichier_info['nom_original']
        type_mime = fichier_info['type_mime']
        taille = fichier_info['taille_bytes']
        
        # Fonction génératrice pour streamer les données par chunks
        def generate():
            chunk_size = 64 * 1024  # 64KB par chunk
            
            # Utiliser un curseur serveur pour éviter de charger tout en mémoire
            cursor_name = f'file_cursor_{fichier_id}'
            
            with get_db() as conn_stream:
                with conn_stream.cursor(name=cursor_name) as cur_stream:
                    cur_stream.execute('''
                        SELECT donnees 
                        FROM fichiers_paiements 
                        WHERE id = %s AND user_id = %s
                    ''', (fichier_id, user_id))
                    
                    # PostgreSQL retourne un memoryview ou bytes
                    result = cur_stream.fetchone()
                    if result and result['donnees']:
                        donnees = bytes(result['donnees'])
                        
                        # Streamer par chunks
                        for i in range(0, len(donnees), chunk_size):
                            yield donnees[i:i + chunk_size]
        
        # Créer la réponse avec streaming
        response = Response(
            stream_with_context(generate()),
            mimetype=type_mime,
            headers={
                'Content-Disposition': f'attachment; filename="{nom_fichier}"',
                'Content-Length': str(taille),
                'Cache-Control': 'no-cache'
            }
        )
        
        return response
        
    except Exception as e:
        print(f"❌ Erreur download fichier: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
# 4. Supprimer un fichier
@app.route('/api/fichiers/<int:fichier_id>', methods=['DELETE'])
def delete_fichier(fichier_id):
    """Supprimer un fichier"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Vérifier si le fichier existe et appartient à l'utilisateur
        cur.execute('SELECT id FROM fichiers_paiements WHERE id = %s AND user_id = %s', 
                   (fichier_id, user_id))
        
        if not cur.fetchone():
            return jsonify({'erreur': 'Fichier non trouvé'}), 404
        
        # Supprimer le fichier
        cur.execute('DELETE FROM fichiers_paiements WHERE id = %s AND user_id = %s', 
                   (fichier_id, user_id))
        
        conn.commit()
        
        return jsonify({'message': 'Fichier supprimé avec succès'})
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur delete fichier: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 5. Visualiser un fichier (stream)
file_cache = {}
CACHE_MAX_SIZE = 10 * 1024 * 1024  # 10MB max en cache

@app.route('/api/fichiers/<int:fichier_id>/view', methods=['GET'])
def view_fichier(fichier_id):
    """Visualiser un fichier avec optimisations"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    # Clé de cache
    cache_key = f"{user_id}_{fichier_id}"
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Récupérer les métadonnées
        cur.execute('''
            SELECT nom_original, type_mime, taille_bytes, date_upload
            FROM fichiers_paiements 
            WHERE id = %s AND user_id = %s
        ''', (fichier_id, user_id))
        
        fichier_info = cur.fetchone()
        
        if not fichier_info:
            return jsonify({'erreur': 'Fichier non trouvé'}), 404
        
        type_mime = fichier_info['type_mime']
        taille = fichier_info['taille_bytes']
        nom_fichier = fichier_info['nom_original']
        date_upload = fichier_info['date_upload']
        
        # Vérifier si le fichier est en cache
        if cache_key in file_cache:
            cached_data, cached_date = file_cache[cache_key]
            if cached_date == date_upload:
                print(f"✅ Cache hit pour fichier {fichier_id}")
                return Response(
                    cached_data,
                    mimetype=type_mime,
                    headers={'Cache-Control': 'public, max-age=3600'}
                )
        
        # Si fichier petit (< 1MB), le mettre en cache
        if taille < 1 * 1024 * 1024:
            cur.execute('''
                SELECT donnees 
                FROM fichiers_paiements 
                WHERE id = %s AND user_id = %s
            ''', (fichier_id, user_id))
            
            result = cur.fetchone()
            if result and result['donnees']:
                donnees = bytes(result['donnees'])
                
                # Ajouter au cache si possible
                current_cache_size = sum(len(v[0]) for v in file_cache.values())
                if current_cache_size + len(donnees) < CACHE_MAX_SIZE:
                    file_cache[cache_key] = (donnees, date_upload)
                    print(f"✅ Fichier {fichier_id} ajouté au cache")
                
                return Response(
                    donnees,
                    mimetype=type_mime,
                    headers={'Cache-Control': 'public, max-age=3600'}
                )
        
        # Pour les gros fichiers, utiliser le streaming
        def generate_large():
            chunk_size = 128 * 1024  # 128KB
            
            with get_db() as conn_stream:
                with conn_stream.cursor() as cur_stream:
                    cur_stream.execute('''
                        SELECT donnees 
                        FROM fichiers_paiements 
                        WHERE id = %s AND user_id = %s
                    ''', (fichier_id, user_id))
                    
                    result = cur_stream.fetchone()
                    if result and result['donnees']:
                        donnees = bytes(result['donnees'])
                        
                        for i in range(0, len(donnees), chunk_size):
                            yield donnees[i:i + chunk_size]
        
        # Images et PDF peuvent être affichés directement
        if type_mime.startswith('image/') or type_mime == 'application/pdf':
            return Response(
                stream_with_context(generate_large()),
                mimetype=type_mime,
                headers={
                    'Cache-Control': 'public, max-age=3600',
                    'Content-Length': str(taille)
                }
            )
        else:
            # Autres types: forcer le téléchargement
            return Response(
                stream_with_context(generate_large()),
                mimetype=type_mime,
                headers={
                    'Content-Disposition': f'attachment; filename="{nom_fichier}"',
                    'Content-Length': str(taille)
                }
            )
        
    except Exception as e:
        print(f"❌ Erreur view fichier: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
# ================================================
# SOUS-FAMILLES EXAMENS - CRUD COMPLET
# ================================================

# 1. GET - Lister toutes les sous-familles
@app.route('/api/sous-familles-examens', methods=['GET'])
def get_all_sous_familles():
    """Retourne toutes les sous-familles d'examens"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    famille = request.args.get('famille')  # HISTO, BIOPS, CYTO, FCV, IMMUN, AUTRE
    actif = request.args.get('actif', 'true').lower() == 'true'
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        query = '''
            SELECT * FROM sous_familles_examens 
            WHERE (user_id = %s OR user_id = 'system')
        '''
        params = [user_id]
        
        if actif:
            query += ' AND actif = TRUE'
        
        if famille:
            query += ' AND famille = %s'
            params.append(famille)
        
        query += ' ORDER BY famille, designation'
        
        cur.execute(query, params)
        sous_familles = cur.fetchall()
        
        # Formater les résultats
        result = []
        for sf in sous_familles:
            item = dict(sf)
            # Ajouter un libellé pour l'affichage
            item['libelle'] = f"{item['designation']} ({float(item['prix']):.0f} DA)"
            result.append(item)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur get_all_sous_familles: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 2. GET - Récupérer une sous-famille par ID
@app.route('/api/sous-familles-examens/<int:id>', methods=['GET'])
def get_sous_famille(id):
    """Retourne une sous-famille par ID"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM sous_familles_examens 
            WHERE id = %s AND (user_id = %s OR user_id = 'system')
        ''', (id, user_id))
        
        sous_famille = cur.fetchone()
        
        if not sous_famille:
            return jsonify({'erreur': 'Sous-famille non trouvée'}), 404
        
        result = dict(sous_famille)
        result['libelle'] = f"{result['designation']} ({float(result['prix']):.0f} DA)"
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur get_sous_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 3. POST - Créer une nouvelle sous-famille
@app.route('/api/sous-familles-examens', methods=['POST'])
def create_sous_famille():
    """Crée une nouvelle sous-famille d'examen"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    data = request.json
    required = ['famille', 'code', 'designation', 'prix']
    
    if not data or any(k not in data for k in required):
        return jsonify({'erreur': 'Champs obligatoires: famille, code, designation, prix'}), 400
    
    # Valider que la famille est valide (optionnel)
    familles_valides = ['HISTO', 'BIOPS', 'CYTO', 'FCV', 'IMMUN', 'AUTRE']
    if data['famille'] not in familles_valides:
        return jsonify({'erreur': f'Famille invalide. Valeurs acceptées: {", ".join(familles_valides)}'}), 400
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Vérifier si le code existe déjà
        cur.execute('SELECT id FROM sous_familles_examens WHERE user_id = %s AND code = %s', 
                   (user_id, data['code']))
        if cur.fetchone():
            return jsonify({'erreur': 'Ce code existe déjà'}), 400
        
        # Insérer la nouvelle sous-famille
        cur.execute('''
            INSERT INTO sous_familles_examens (
                user_id, famille, code, designation, 
                description, prix, actif
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, code, designation, famille, prix
        ''', (
            user_id,
            data['famille'],
            data['code'],
            data['designation'],
            data.get('description'),
            float(data['prix']),
            data.get('actif', True)
        ))
        
        new_sf = cur.fetchone()
        conn.commit()
        
        result = dict(new_sf)
        result['message'] = 'Sous-famille créée avec succès'
        
        return jsonify(result), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur create_sous_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 4. PUT - Mettre à jour une sous-famille
@app.route('/api/sous-familles-examens/<int:id>', methods=['PUT'])
def update_sous_famille(id):
    """Met à jour une sous-famille existante"""
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
        
        # Vérifier que la sous-famille existe et appartient à l'utilisateur
        cur.execute('SELECT id FROM sous_familles_examens WHERE id = %s AND user_id = %s', 
                   (id, user_id))
        
        if not cur.fetchone():
            return jsonify({'erreur': 'Sous-famille non trouvée ou non autorisée'}), 404
        
        # Mise à jour
        update_fields = []
        params = []
        
        # Champs modifiables
        champs_modifiables = ['code', 'designation', 'description', 'prix', 'actif', 'famille']
        
        for champ in champs_modifiables:
            if champ in data:
                update_fields.append(f"{champ} = %s")
                params.append(data[champ])
        
        if not update_fields:
            return jsonify({'erreur': 'Aucun champ à modifier'}), 400
        
        # Ajouter updated_at et les conditions WHERE
        update_fields.append('updated_at = CURRENT_TIMESTAMP')
        params.extend([id, user_id])
        
        query = f'''
            UPDATE sous_familles_examens 
            SET {', '.join(update_fields)}
            WHERE id = %s AND user_id = %s
            RETURNING id, code, designation, famille, prix, actif
        '''
        
        cur.execute(query, params)
        updated = cur.fetchone()
        conn.commit()
        
        if not updated:
            return jsonify({'erreur': 'Échec de la mise à jour'}), 500
        
        result = dict(updated)
        result['message'] = 'Sous-famille mise à jour avec succès'
        
        return jsonify(result)
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur update_sous_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 5. DELETE - Supprimer (désactiver) une sous-famille
@app.route('/api/sous-familles-examens/<int:id>', methods=['DELETE'])
def delete_sous_famille(id):
    """Désactive une sous-famille"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Vérifier que la sous-famille existe
        cur.execute('''
            SELECT id, designation FROM sous_familles_examens 
            WHERE id = %s AND user_id = %s
        ''', (id, user_id))
        
        sous_famille = cur.fetchone()
        if not sous_famille:
            return jsonify({'erreur': 'Sous-famille non trouvée ou non autorisée'}), 404
        
        # Désactiver la sous-famille
        cur.execute('''
            UPDATE sous_familles_examens 
            SET actif = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
        ''', (id, user_id))
        
        conn.commit()
        
        return jsonify({
            'message': f'Sous-famille "{sous_famille["designation"]}" désactivée',
            'id': id,
            'actif': False
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur delete_sous_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 6. GET - Sous-familles par famille
@app.route('/api/sous-familles-examens/famille/<string:famille>', methods=['GET'])
def get_sous_familles_par_famille(famille):
    """Retourne les sous-familles d'une famille spécifique"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM sous_familles_examens
            WHERE famille = %s 
            AND (user_id = %s OR user_id = 'system')
            AND actif = TRUE
            ORDER BY designation
        ''', (famille, user_id))
        
        sous_familles = cur.fetchall()
        
        formatted = []
        for sf in sous_familles:
            sf_dict = dict(sf)
            sf_dict['libelle'] = f"{sf_dict['designation']} ({float(sf_dict['prix']):.0f} DA)"
            formatted.append(sf_dict)
        
        return jsonify({
            'famille': famille,
            'sous_familles': formatted,
            'count': len(formatted)
        })
        
    except Exception as e:
        print(f"❌ Erreur get_sous_familles_par_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 7. GET - Toutes les sous-familles groupées par famille
@app.route('/api/sous-familles-examens/grouped', methods=['GET'])
def get_sous_familles_grouped():
    """Retourne toutes les sous-familles groupées par famille"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Récupérer toutes les sous-familles actives
        cur.execute('''
            SELECT * FROM sous_familles_examens
            WHERE (user_id = %s OR user_id = 'system')
            AND actif = TRUE
            ORDER BY famille, designation
        ''', (user_id,))
        
        sous_familles = cur.fetchall()
        
        # Grouper par famille
        result = {}
        familles = ['HISTO', 'BIOPS', 'CYTO', 'FCV', 'IMMUN', 'AUTRE']
        for famille in familles:
            result[famille] = []
        
        for sf in sous_familles:
            sf_dict = dict(sf)
            sf_dict['libelle'] = f"{sf_dict['designation']} ({float(sf_dict['prix']):.0f} DA)"
            result[sf_dict['famille']].append(sf_dict)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur get_sous_familles_grouped: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 8. GET - Rechercher des sous-familles
@app.route('/api/sous-familles-examens/search', methods=['GET'])
def search_sous_familles():
    """Recherche des sous-familles par terme"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    search_term = request.args.get('q', '')
    if not search_term or len(search_term) < 2:
        return jsonify({'sous_familles': [], 'count': 0})
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM sous_familles_examens
            WHERE (user_id = %s OR user_id = 'system')
            AND actif = TRUE
            AND (designation ILIKE %s OR code ILIKE %s OR description ILIKE %s)
            ORDER BY famille, designation
            LIMIT 20
        ''', (user_id, f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        
        sous_familles = cur.fetchall()
        
        formatted = []
        for sf in sous_familles:
            sf_dict = dict(sf)
            sf_dict['libelle'] = f"{sf_dict['designation']} ({float(sf_dict['prix']):.0f} DA)"
            formatted.append(sf_dict)
        
        return jsonify({
            'sous_familles': formatted,
            'count': len(formatted)
        })
        
    except Exception as e:
        print(f"❌ Erreur search_sous_familles: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 9. POST - Dupliquer une sous-famille
@app.route('/api/sous-familles-examens/<int:id>/duplicate', methods=['POST'])
def duplicate_sous_famille(id):
    """Duplique une sous-famille existante"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'erreur': 'X-User-ID manquant'}), 401
    
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Récupérer la sous-famille à dupliquer
        cur.execute('''
            SELECT * FROM sous_familles_examens 
            WHERE id = %s AND (user_id = %s OR user_id = 'system')
        ''', (id, user_id))
        
        original = cur.fetchone()
        if not original:
            return jsonify({'erreur': 'Sous-famille non trouvée'}), 404
        
        original_dict = dict(original)
        
        # Générer un nouveau code
        base_code = original_dict['code']
        counter = 1
        new_code = f"{base_code}_COPY{counter}"
        
        # Chercher un code disponible
        while True:
            cur.execute('SELECT id FROM sous_familles_examens WHERE user_id = %s AND code = %s', 
                       (user_id, new_code))
            if not cur.fetchone():
                break
            counter += 1
            new_code = f"{base_code}_COPY{counter}"
        
        # Insérer la copie
        cur.execute('''
            INSERT INTO sous_familles_examens (
                user_id, famille, code, designation, 
                description, prix, actif
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, code, designation, famille, prix
        ''', (
            user_id,
            original_dict['famille'],
            new_code,
            f"{original_dict['designation']} (Copie)",
            original_dict['description'],
            original_dict['prix'],
            original_dict['actif']
        ))
        
        new_sf = cur.fetchone()
        conn.commit()
        
        result = dict(new_sf)
        result['message'] = 'Sous-famille dupliquée avec succès'
        
        return jsonify(result), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur duplicate_sous_famille: {str(e)}")
        return jsonify({'erreur': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
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
            
            # ✅ CORRECTION : Requête COUNT séparée et simplifiée
            count_query = '''
                SELECT COUNT(*) as total
                FROM paiements p
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
            
            # Exécuter le count
            cur.execute(count_query, count_params)
            total_result = cur.fetchone()
            total_count = total_result['total'] if total_result else 0
            
            # Ajouter la pagination à la requête principale
            query += ' LIMIT %s OFFSET %s'
            params.extend([per_page, offset])
            
            # Exécuter la requête principale
            cur.execute(query, params)
            payments = cur.fetchall()
            
            # Formater les résultats
            formatted_payments = []
            for p in payments:
                payment_dict = dict(p)
                
                # Créer le nom complet du patient
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
            type_paiement = data.get('type_paiement', 'consultation')
            
            print(f"📝 Début enregistrement paiement:")
            print(f"   - User ID: {user_id}")
            print(f"   - Type examen: {type_paiement}")
            print(f"   - Mode: {mode_paiement}")
            print(f"   - Montant: {montant_paye}")
            
            # ✅ GÉNÉRATION AUTOMATIQUE DU NUMÉRO DE REÇU
            numero_cr = data.get('numero_cr', '').strip()
            if not numero_cr:
                print(f"🔄 Génération automatique du numéro...")
                numero_cr = generer_numero_recu(user_id, type_paiement)
                print(f"✅ Numéro de reçu généré: {numero_cr}")
            else:
                print(f"📌 Numéro de reçu fourni: {numero_cr}")
            
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
            
            print(f"💾 Insertion dans la base de données...")
            
            # ✅ INSERTION DU PAIEMENT AVEC LE NUMÉRO
            cur.execute('''
                INSERT INTO paiements (
                    user_id, patient_id, utilisateur_id, montant, 
                    type_paiement, mode_paiement, montant_total,
                    numero_cr, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, date_paiement, numero_cr
            ''', (
                user_id,
                data['patient_id'],
                utilisateur_id,
                montant_paye,
                type_paiement,
                mode_paiement,
                montant_total,
                numero_cr,
                data.get('notes')
            ))
            
            new_payment = cur.fetchone()
            
            print(f"✅ Paiement inséré:")
            print(f"   - ID: {new_payment['id']}")
            print(f"   - Numéro CR: {new_payment['numero_cr']}")
            print(f"   - Date: {new_payment['date_paiement']}")
            
            # Calculer le nouveau solde selon le mode de paiement
            if mode_paiement == 'a_terme':
                reste_a_payer = montant_total - montant_paye
                nouveau_solde = solde_actuel - reste_a_payer
                message = f'Paiement à terme enregistré. Reste à payer: {reste_a_payer:.2f} DA'
                
                cur.execute('''
                    UPDATE patients 
                    SET solde = %s
                    WHERE id = %s AND user_id = %s
                ''', (nouveau_solde, data['patient_id'], user_id))
                
            elif mode_paiement == 'paiement_partiel':
                nouveau_solde = solde_actuel + montant_paye
                message = f'Paiement partiel enregistré. Nouveau solde: {nouveau_solde:.2f} DA'
                
                cur.execute('''
                    UPDATE patients 
                    SET solde = %s
                    WHERE id = %s AND user_id = %s
                ''', (nouveau_solde, data['patient_id'], user_id))
                
            else:  # espece (comptant)
                nouveau_solde = solde_actuel
                message = f'Paiement comptant enregistré: {montant_paye:.2f} DA'
            
            conn.commit()
            
            print(f"✅ Transaction validée (commit)")
            
            # Vérifier que le compteur a bien été créé/mis à jour
            cur.execute('''
                SELECT * FROM compteurs_recus 
                WHERE user_id = %s AND type_examen = %s
                ORDER BY updated_at DESC LIMIT 1
            ''', (user_id, type_paiement.lower()))
            
            compteur_info = cur.fetchone()
            if compteur_info:
                print(f"📊 Compteur actuel: {dict(compteur_info)}")
            else:
                print(f"⚠️ ATTENTION: Aucun compteur trouvé pour {type_paiement}!")
            
            result = dict(new_payment)
            result['nouveau_solde'] = nouveau_solde
            result['message'] = message
            result['paiement_id'] = result['id']
            
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
        
        # ✅ AJOUT IMPORTANT : Statistiques du jour
        aujourdhui = datetime.now().strftime('%Y-%m-%d')
        
        # Total encaisse du jour
        cur.execute('''
            SELECT COALESCE(SUM(montant), 0) as total_jour
            FROM paiements
            WHERE user_id = %s AND DATE(date_paiement) = %s
        ''', (user_id, aujourdhui))
        encaisse_jour = cur.fetchone()
        
        # Total encaisse global
        cur.execute('''
            SELECT COALESCE(SUM(montant), 0) as total_global
            FROM paiements
            WHERE user_id = %s
        ''', (user_id,))
        encaisse_totale = cur.fetchone()
        
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
            # ✅ NOUVEAU : Données du jour
            'total_encaisse_jour': float(encaisse_jour['total_jour']) if encaisse_jour else 0,
            'total_encaisse': float(encaisse_totale['total_global']) if encaisse_totale else 0,
            
            # Données existantes
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
