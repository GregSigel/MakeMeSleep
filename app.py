import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import base64
import re

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-makemedream')

# Base de données
db_url = os.getenv('DATABASE_URL', 'sqlite:///makemedream.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration du stockage des fichiers
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'mp4', 'webm', 'mp3', 'ogg', 'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODÈLES DE DONNÉES ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    channel = db.relationship('Channel', backref='owner', uselist=False, cascade="all, delete-orphan")

class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    videos = db.relationship('Video', backref='channel', lazy=True, cascade="all, delete-orphan")

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    thumbnail = db.Column(db.String(500), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Utilitaires de fichier
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file_or_get_url(file_obj, url_input, default_fallback=""):
    if file_obj and file_obj.filename != '' and allowed_file(file_obj.filename):
        filename = secure_filename(f"{int(datetime.now().timestamp())}_{file_obj.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_obj.save(filepath)
        return url_for('static', filename=f'uploads/{filename}')
    elif url_input:
        return url_input.strip()
    return default_fallback

# Initialisation du compte admin système depuis .env
def init_admin_account():
    admin_user = os.getenv('ADMIN_USERNAME')
    admin_pass = os.getenv('ADMIN_PASSWORD')

    if admin_user and admin_pass:
        user = User.query.filter_by(username=admin_user).first()
        hashed_pwd = generate_password_hash(admin_pass, method='pbkdf2:sha256')
        if not user:
            user = User(username=admin_user, password=hashed_pwd, is_admin=True)
            db.session.add(user)
            db.session.flush()
            channel = Channel(name="MakeMeDream Officiel", description="Chaîne d'administration officielle", user_id=user.id)
            db.session.add(channel)
            db.session.commit()
        else:
            user.password = hashed_pwd
            user.is_admin = True
            db.session.commit()

def save_b64_image(b64_str):
    if not b64_str or not b64_str.startswith('data:image'):
        return None
    try:
        header, encoded = b64_str.split(',', 1)
        data = base64.b64decode(encoded)
        filename = f"thumb_auto_{int(datetime.now().timestamp())}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(data)
        return url_for('static', filename=f'uploads/{filename}')
    except Exception:
        return None

def process_youtube_url(url):
    """
    Extrait l'ID de la vidéo YouTube et retourne l'URL d'intégration Embed et la miniature.
    """
    if not url:
        return None, None
        
    # Motif RegEx pour capturer l'ID YouTube (shorts, watch, youtu.be)
    youtube_regex = r'(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(youtube_regex, url)
    
    if match:
        video_id = match.group(1)
        embed_url = f"https://www.youtube.com/embed/{video_id}"
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        return embed_url, thumbnail_url
        
    return url, None

# --- ROUTES ---

@app.route('/')
def index():
    selected_category = request.args.get('category', 'Tout')
    categories = ["Tout", "ASMR", "Bruits Blancs", "Histoires", "Méditation", "Sommeil"]
    
    if selected_category != 'Tout':
        videos = Video.query.filter(Video.category.ilike(selected_category)).order_by(Video.created_at.desc()).all()
    else:
        videos = Video.query.order_by(Video.created_at.desc()).all()

    return render_template('index.html', videos=videos, categories=categories, selected_category=selected_category)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    categories = ["Tout", "ASMR", "Bruits Blancs", "Histoires", "Méditation", "Sommeil"]
    videos = []
    if query:
        videos = Video.query.filter(
            (Video.title.ilike(f"%{query}%")) | (Video.category.ilike(f"%{query}%"))
        ).order_by(Video.created_at.desc()).all()
    return render_template('index.html', videos=videos, categories=categories, selected_category="Tout", search_query=query)

@app.route('/watch/<int:video_id>')
def watch(video_id):
    video = Video.query.get_or_404(video_id)
    video.views += 1
    db.session.commit()

    recommendations = Video.query.filter(Video.id != video.id).order_by(Video.created_at.desc()).limit(6).all()
    return render_template('watch.html', video=video, recommendations=recommendations)

# --- AUTHENTIFICATION ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        channel_name = request.form.get('channel_name', '').strip() or f"Chaîne de {username}"

        if not username or not password or password != confirm_password or len(password) < 6:
            flash("Vérifiez la validité de vos saisies.", "error")
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash("Ce pseudo est déjà pris.", "error")
            return render_template('register.html')

        hashed_pwd = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pwd)
        db.session.add(new_user)
        db.session.flush()

        new_channel = Channel(name=channel_name, description="Bienvenue sur ma chaîne !", user_id=new_user.id)
        db.session.add(new_channel)
        db.session.commit()

        login_user(new_user)
        flash("Compte créé avec succès.", "success")
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.password and check_password_hash(user.password, password):
            login_user(user)
            flash("Connexion réussie.", "success")
            return redirect(url_for('admin_panel' if user.is_admin else 'index'))
        
        flash("Identifiants incorrects.", "error")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for('index'))

# --- ESPACE D'ADMINISTRATION ---

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Accès réservé aux administrateurs.", "error")
        return redirect(url_for('index'))

    categories = ["ASMR", "Bruits Blancs", "Histoires", "Méditation", "Sommeil"]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        description = request.form.get('description', '').strip()
        
        # Gestion vidéo (fichier vs URL)
        video_file = request.files.get('video_file')
        video_url_input = request.form.get('video_url')
        final_video_url = save_file_or_get_url(video_file, video_url_input)

        # Gestion vignette (fichier vs URL)
        thumb_file = request.files.get('thumb_file')
        thumb_url_input = request.form.get('thumb_url')
        default_thumb = "https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=500&q=80"
        final_thumb_url = save_file_or_get_url(thumb_file, thumb_url_input, default_fallback=default_thumb)

        if not title or not category or not final_video_url:
            flash("Veuillez remplir le titre, la catégorie et fournir une vidéo (fichier ou URL).", "error")
        else:
            new_video = Video(
                title=title,
                category=category,
                description=description,
                video_url=final_video_url,
                thumbnail=final_thumb_url,
                channel_id=current_user.channel.id
            )
            db.session.add(new_video)
            db.session.commit()
            flash("Vidéo publiée avec succès !", "success")
            return redirect(url_for('admin_panel'))

    videos = Video.query.order_by(Video.created_at.desc()).all()
    users = User.query.all()
    return render_template('admin.html', videos=videos, users=users, categories=categories)

@app.route('/admin/delete-video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    if not current_user.is_admin:
        return "Accès interdit", 403

    video = Video.query.get_or_404(video_id)
    # Suppression du fichier disque local s'il existe
    if video.video_url.startswith('/static/uploads/'):
        local_path = os.path.join(app.root_path, video.video_url.lstrip('/'))
        if os.path.exists(local_path):
            os.remove(local_path)

    db.session.delete(video)
    db.session.commit()
    flash("Vidéo supprimée avec succès.", "info")
    return redirect(url_for('admin_panel'))

# --- MON PROFIL ---

@app.route('/profile')
@login_required
def profile():
    user_videos = []
    if current_user.channel:
        user_videos = Video.query.filter_by(channel_id=current_user.channel.id).order_by(Video.created_at.desc()).all()
    return render_template('profile.html', user_videos=user_videos)

@app.route('/profile/update-channel', methods=['POST'])
@login_required
def update_channel():
    channel_name = request.form.get('channel_name', '').strip()
    description = request.form.get('description', '').strip()

    if channel_name and current_user.channel:
        conflict = Channel.query.filter(Channel.name == channel_name, Channel.id != current_user.channel.id).first()
        if conflict:
            flash("Ce nom de chaîne est déjà pris.", "error")
            return redirect(url_for('profile'))

        current_user.channel.name = channel_name
        current_user.channel.description = description
        db.session.commit()
        flash("Informations de votre chaîne mises à jour.", "success")

    return redirect(url_for('profile'))

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    current_pwd = request.form.get('current_password')
    new_pwd = request.form.get('new_password')
    confirm_pwd = request.form.get('confirm_password')

    if not current_user.password:
        flash("Modification impossible pour ce type de compte.", "error")
        return redirect(url_for('profile'))

    if not check_password_hash(current_user.password, current_pwd):
        flash("Mot de passe actuel incorrect.", "error")
        return redirect(url_for('profile'))

    if new_pwd != confirm_pwd:
        flash("Les nouveaux mots de passe ne correspondent pas.", "error")
        return redirect(url_for('profile'))

    if len(new_pwd) < 6:
        flash("Le nouveau mot de passe doit faire au moins 6 caractères.", "error")
        return redirect(url_for('profile'))

    current_user.password = generate_password_hash(new_pwd, method='pbkdf2:sha256')
    db.session.commit()
    flash("Mot de passe modifié avec succès.", "success")
    return redirect(url_for('profile'))

@app.route('/profile/delete', methods=['POST'])
@login_required
def delete_account():
    user = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user)
    db.session.commit()
    flash("Votre compte et votre chaîne ont été supprimés.", "info")
    return redirect(url_for('index'))


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # Sécurité : s'assurer que l'utilisateur a une chaîne d'utilisateurs
    if not current_user.channel:
        new_channel = Channel(name=f"Chaîne de {current_user.username}", user_id=current_user.id)
        db.session.add(new_channel)
        db.session.commit()

    categories = ["ASMR", "Bruits Blancs", "Histoires", "Méditation", "Sommeil"]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        description = request.form.get('description', '').strip()

        video_file = request.files.get('video_file')
        video_url_input = request.form.get('video_url', '').strip()

        final_video_url = save_file_or_get_url(video_file, video_url_input)
        
        # Traitement YouTube si c'est un lien externe
        yt_embed_url, yt_thumb_url = process_youtube_url(final_video_url)
        if yt_embed_url:
            final_video_url = yt_embed_url

        # Traitement miniature
        thumb_file = request.files.get('thumb_file')
        thumb_url_input = request.form.get('thumb_url')
        thumb_b64 = request.form.get('generated_thumb')

        final_thumb_url = save_file_or_get_url(thumb_file, thumb_url_input)
        
        if not final_thumb_url and yt_thumb_url:
            # Utilise automatiquement la miniature YouTube si disponible
            final_thumb_url = yt_thumb_url
        elif not final_thumb_url and thumb_b64:
            final_thumb_url = save_b64_image(thumb_b64)

        if not final_thumb_url:
            final_thumb_url = "https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=500&q=80"

        if not title or not category or not final_video_url:
            flash("Veuillez remplir le titre, la catégorie et fournir une vidéo.", "error")
        else:
            new_video = Video(
                title=title,
                category=category,
                description=description,
                video_url=final_video_url,
                thumbnail=final_thumb_url,
                channel_id=current_user.channel.id
            )
            db.session.add(new_video)
            db.session.commit()
            flash("Vidéo publiée avec succès !", "success")
            return redirect(url_for('watch', video_id=new_video.id))

    return render_template('upload.html', categories=categories)

@app.route('/video/<int:video_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    # Vérification de propriété (seul l'auteur ou l'admin peut modifier)
    if video.channel.user_id != current_user.id and not current_user.is_admin:
        flash("Vous n'avez pas l'autorisation de modifier cette vidéo.", "error")
        return redirect(url_for('watch', video_id=video.id))

    categories = ["ASMR", "Bruits Blancs", "Histoires", "Méditation", "Sommeil"]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        description = request.form.get('description', '').strip()

        if not title or not category:
            flash("Le titre et la catégorie sont obligatoires.", "error")
            return render_template('edit_video.html', video=video, categories=categories)

        # Mise à jour des champs de base
        video.title = title
        video.category = category
        video.description = description

        # Remplacement optionnel de la vidéo (fichier ou URL)
        video_file = request.files.get('video_file')
        video_url_input = request.form.get('video_url', '').strip()
        if video_file or video_url_input:
            new_video_url = save_file_or_get_url(video_file, video_url_input)
            if new_video_url:
                yt_embed_url, yt_thumb_url = process_youtube_url(new_video_url)
                video.video_url = yt_embed_url if yt_embed_url else new_video_url
                if yt_thumb_url and not request.files.get('thumb_file') and not request.form.get('thumb_url'):
                    video.thumbnail = yt_thumb_url

        # Remplacement optionnel de la miniature
        thumb_file = request.files.get('thumb_file')
        thumb_url_input = request.form.get('thumb_url', '').strip()
        thumb_b64 = request.form.get('generated_thumb')

        new_thumb = save_file_or_get_url(thumb_file, thumb_url_input)
        if new_thumb:
            video.thumbnail = new_thumb
        elif thumb_b64:
            saved_b64 = save_b64_image(thumb_b64)
            if saved_b64:
                video.thumbnail = saved_b64

        db.session.commit()
        flash("Vidéo mise à jour avec succès !", "success")
        return redirect(url_for('watch', video_id=video.id))

    return render_template('edit_video.html', video=video, categories=categories)


@app.route('/video/<int:video_id>/delete', methods=['POST'])
@login_required
def delete_user_video(video_id):
    video = Video.query.get_or_404(video_id)

    # Vérification de propriété
    if video.channel.user_id != current_user.id and not current_user.is_admin:
        flash("Vous n'avez pas l'autorisation de supprimer cette vidéo.", "error")
        return redirect(url_for('watch', video_id=video.id))

    # Suppression du fichier vidéo local du serveur s'il existe
    if video.video_url.startswith('/static/uploads/'):
        local_path = os.path.join(app.root_path, video.video_url.lstrip('/'))
        if os.path.exists(local_path):
            os.remove(local_path)

    # Suppression de la miniature locale du serveur si elle existe
    if video.thumbnail.startswith('/static/uploads/'):
        local_thumb = os.path.join(app.root_path, video.thumbnail.lstrip('/'))
        if os.path.exists(local_thumb):
            os.remove(local_thumb)

    db.session.delete(video)
    db.session.commit()
    flash("Vidéo supprimée avec succès.", "info")
    return redirect(url_for('profile'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_admin_account()
    app.run(debug=True, port=5000)