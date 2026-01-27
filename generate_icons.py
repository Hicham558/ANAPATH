#!/usr/bin/env python3
"""
Script de génération automatique des icônes PWA pour ANAPATH ELYOUSR
Nécessite Pillow : pip install Pillow
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Tailles d'icônes PWA requises
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# Couleurs
BACKGROUND_COLOR = "#4f46e5"  # Indigo
ICON_COLOR = "#ffffff"  # Blanc

def create_icon_folder():
    """Créer le dossier icons s'il n'existe pas"""
    if not os.path.exists('icons'):
        os.makedirs('icons')
        print("✅ Dossier 'icons' créé")

def create_simple_icon(size):
    """
    Créer une icône simple avec les initiales ANAPATH
    """
    # Créer une image carrée avec fond coloré
    img = Image.new('RGB', (size, size), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Ajouter un cercle blanc au centre
    circle_radius = size // 3
    center = size // 2
    
    # Dessiner un cercle
    circle_bbox = [
        center - circle_radius,
        center - circle_radius,
        center + circle_radius,
        center + circle_radius
    ]
    draw.ellipse(circle_bbox, fill=ICON_COLOR)
    
    # Ajouter du texte "A" au centre
    try:
        # Essayer de charger une police (peut ne pas fonctionner sur tous les systèmes)
        font_size = size // 3
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        # Utiliser la police par défaut si la police TrueType n'est pas disponible
        font = ImageFont.load_default()
    
    text = "A"
    
    # Centrer le texte
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    text_x = (size - text_width) // 2
    text_y = (size - text_height) // 2 - bbox[1]
    
    draw.text((text_x, text_y), text, fill=BACKGROUND_COLOR, font=font)
    
    return img

def create_medical_icon(size):
    """
    Créer une icône avec symbole médical (microscope stylisé)
    """
    img = Image.new('RGB', (size, size), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Paramètres de taille proportionnels
    padding = size // 6
    
    # Dessiner un microscope stylisé
    # Base
    base_y = size - padding
    base_height = size // 15
    draw.rectangle([
        padding, base_y - base_height,
        size - padding, base_y
    ], fill=ICON_COLOR)
    
    # Corps du microscope
    body_width = size // 8
    body_x = size // 2 - body_width // 2
    body_height = size // 2
    draw.rectangle([
        body_x, base_y - base_height - body_height,
        body_x + body_width, base_y - base_height
    ], fill=ICON_COLOR)
    
    # Tête (objectif)
    head_size = size // 4
    head_x = size // 2 - head_size // 2
    head_y = padding
    draw.ellipse([
        head_x, head_y,
        head_x + head_size, head_y + head_size
    ], fill=ICON_COLOR)
    
    # Oculaires (2 cercles)
    ocular_size = size // 10
    ocular_spacing = size // 20
    
    # Oculaire gauche
    draw.ellipse([
        head_x + head_size // 4 - ocular_size // 2, head_y + head_size - ocular_size,
        head_x + head_size // 4 + ocular_size // 2, head_y + head_size
    ], fill=BACKGROUND_COLOR)
    
    # Oculaire droit
    draw.ellipse([
        head_x + 3 * head_size // 4 - ocular_size // 2, head_y + head_size - ocular_size,
        head_x + 3 * head_size // 4 + ocular_size // 2, head_y + head_size
    ], fill=BACKGROUND_COLOR)
    
    return img

def generate_all_icons(style='simple'):
    """
    Générer toutes les icônes aux tailles requises
    
    Args:
        style: 'simple' ou 'medical'
    """
    create_icon_folder()
    
    print(f"\n🎨 Génération des icônes PWA (style: {style})...\n")
    
    for size in ICON_SIZES:
        if style == 'medical':
            img = create_medical_icon(size)
        else:
            img = create_simple_icon(size)
        
        filename = f'icons/icon-{size}x{size}.png'
        img.save(filename, 'PNG')
        print(f"✅ {filename} créée ({size}x{size})")
    
    print(f"\n✨ {len(ICON_SIZES)} icônes générées avec succès !")
    print("\n📋 Prochaines étapes :")
    print("   1. Vérifiez les icônes dans le dossier 'icons/'")
    print("   2. Si nécessaire, remplacez-les par vos propres designs")
    print("   3. Suivez les instructions dans README_PWA.md")

def create_favicon():
    """Créer un favicon.ico à partir de l'icône 192x192"""
    try:
        img = Image.open('icons/icon-192x192.png')
        img.save('favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
        print("\n✅ favicon.ico créé")
    except Exception as e:
        print(f"\n⚠️  Impossible de créer favicon.ico: {e}")

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("🚀 GÉNÉRATEUR D'ICÔNES PWA - ANAPATH ELYOUSR")
    print("=" * 60)
    
    # Vérifier si Pillow est installé
    try:
        from PIL import Image
    except ImportError:
        print("\n❌ ERREUR : Pillow n'est pas installé")
        print("📦 Installation : pip install Pillow")
        sys.exit(1)
    
    # Choisir le style
    style = 'medical' if len(sys.argv) > 1 and sys.argv[1] == 'medical' else 'simple'
    
    # Générer les icônes
    generate_all_icons(style)
    
    # Créer le favicon
    create_favicon()
    
    print("\n" + "=" * 60)
    print("✨ TERMINÉ !")
    print("=" * 60 + "\n")
