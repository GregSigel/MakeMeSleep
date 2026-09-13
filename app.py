import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-makemedream')

# Base agnostique : PostgreSQL en prod, SQLite en local
db_url = os.getenv('DATABASE_URL', 'sqlite:///makemedream.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODÈLES DE DONNÉES ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True) # Optionnel pour le futur Google Auth
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    # Suppression en cascade : supprimer un user supprime automatiquement sa chaîne
    channel = db.relationship('Channel', backref='owner', uselist=False, cascade="all, delete-orphan")

class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    videos = db.relationship('Video', backref='channel', lazy=True)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    thumbnail = db.Column(db.String(300), nullable=False)
    video_url = db.Column(db.String(300), nullable=True) # URL mp4 ou embed YouTube/Vimeo
    category = db.Column(db.String(50), nullable=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    description = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES ---

@app.route('/')
def index():
    videos = [
        {"id": 1, "title": "Bruits de pluie et tonnerre lointain", "thumb": "https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?w=500&q=80", "category": "Sommeil", "views": "12k", "channel": "Serein&Co"},
        {"id": 2, "title": "ASMR Chuchotements Inaudibles", "thumb": "https://images.unsplash.com/photo-1516750105099-4b8a83e217ee?w=500&q=80", "category": "ASMR", "views": "45k", "channel": "DreamWhispers"},
        {"id": 3, "title": "Lecture d'un conte au coin du feu", "thumb": "https://images.unsplash.com/photo-1478147427282-58a87a120781?w=500&q=80", "category": "Story", "views": "8k", "channel": "NuitsÉtoilées"},
        {"id": 4, "title": "Tapping sur bois et verre", "thumb": "https://images.unsplash.com/photo-1616423640778-28d1b53229bd?w=500&q=80", "category": "ASMR", "views": "23k", "channel": "Relax Lab"}
    ]
    return render_template('index.html', videos=videos)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    videos = [
        {"id": 1, "title": "Bruits de pluie et tonnerre lointain", "thumb": "https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?w=500&q=80", "category": "Sommeil", "views": "12k", "channel": "Serein&Co"},
        {"id": 2, "title": "ASMR Chuchotements Inaudibles", "thumb": "https://images.unsplash.com/photo-1516750105099-4b8a83e217ee?w=500&q=80", "category": "ASMR", "views": "45k", "channel": "DreamWhispers"},
        {"id": 3, "title": "Lecture d'un conte au coin du feu", "thumb": "https://images.unsplash.com/photo-1478147427282-58a87a120781?w=500&q=80", "category": "Story", "views": "8k", "channel": "NuitsÉtoilées"},
        {"id": 4, "title": "Tapping sur bois et verre", "thumb": "https://images.unsplash.com/photo-1616423640778-28d1b53229bd?w=500&q=80", "category": "ASMR", "views": "23k", "channel": "Relax Lab"}
    ]
    filtered = [v for v in videos if query.lower() in v['title'].lower() or query.lower() in v['category'].lower()]
    return render_template('index.html', videos=filtered, search_query=query)

# --- INSCRIPTION CLASSIQUE ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        channel_name = request.form.get('channel_name', '').strip()

        # Validations
        if not username or not password or not confirm_password:
            flash("Veuillez remplir tous les champs obligatoires.", "error")
            return render_template('register.html')

        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template('register.html')

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "error")
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash("Ce pseudo est déjà pris. Choisissez-en un autre.", "error")
            return render_template('register.html')

        # Nom de chaîne par défaut si laissé vide
        if not channel_name:
            channel_name = f"Chaîne de {username}"

        if Channel.query.filter_by(name=channel_name).first():
            flash("Ce nom de chaîne existe déjà. Choisissez un autre nom.", "error")
            return render_template('register.html')

        # Création de l'utilisateur et de sa chaîne
        hashed_pwd = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pwd)
        
        db.session.add(new_user)
        db.session.flush() # Récupère l'ID généré pour l'utilisateur

        new_channel = Channel(
            name=channel_name, 
            description="Bienvenue sur ma chaîne MakeMeDream !", 
            user_id=new_user.id
        )
        db.session.add(new_channel)
        db.session.commit()

        login_user(new_user)
        flash("Compte et chaîne créés avec succès ! Bienvenue dans votre bulle.", "success")
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
            flash("Ravi de vous revoir.", "success")
            return redirect(url_for('index'))
        else:
            flash("Identifiants incorrects, essayez de nouveau.", "error")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for('index'))

# --- GESTION DU PROFIL ET DE LA CHAÎNE ---

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

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
        flash("Modification impossible pour un compte externe.", "error")
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

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Accès réservé aux administrateurs.", 403
    return "Espace d'administration MakeMeDream."

@app.route('/watch/<int:video_id>')
def watch(video_id):
    # Données de démonstration (à remplacer par Video.query.get_or_404(video_id))
    current_video = {
        "id": video_id,
        "title": "Bruits de pluie intense et tonnerre lointain pour s'endormir",
        "video_url": "https://www.w3schools.com/html/mov_bbb.mp4", # Vidéo d'exemple HTML5
        "category": "Sommeil",
        "views": "128 450",
        "created_ago": "Il y a 3 jours",
        "description": "Plongez dans un sommeil profond grâce à cet enregistrement binaural de pluie battante contre le verre. Idéal pour calmer l'anxiété nocturne et lutter contre l'insomnie.\n\n🎧 Écoute au casque recommandée.",
        "channel": {
            "name": "Serein&Co",
            "subscribers": "42,5 k",
            "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&q=80"
        }
    }
    
    # Vidéos suggérées (colonne de droite)
    recommendations = [
        {"id": 2, "title": "ASMR Chuchotements Inaudibles", "thumb": "https://images.unsplash.com/photo-1516750105099-4b8a83e217ee?w=500&q=80", "category": "ASMR", "views": "45k", "created_ago": "Il y a 1 semaine", "channel": "DreamWhispers"},
        {"id": 3, "title": "Lecture d'un conte au coin du feu", "thumb": "https://images.unsplash.com/photo-1478147427282-58a87a120781?w=500&q=80", "category": "Story", "views": "8k", "created_ago": "Il y a 2 semaines", "channel": "NuitsÉtoilées"},
        {"id": 4, "title": "Tapping sur bois et verre", "thumb": "https://images.unsplash.com/photo-1616423640778-28d1b53229bd?w=500&q=80", "category": "ASMR", "views": "23k", "created_ago": "Il y a 1 mois", "channel": "Relax Lab"}
    ]

    return render_template('watch.html', video=current_video, recommendations=recommendations)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            hashed_pwd = generate_password_hash('admin123', method='pbkdf2:sha256')
            admin = User(username='admin', password=hashed_pwd, is_admin=True)
            db.session.add(admin)
            db.session.flush()
            admin_channel = Channel(name="MakeMeDream Officiel", description="Chaîne officielle de la plateforme", user_id=admin.id)
            db.session.add(admin_channel)
            db.session.commit()

    app.run(debug=True, port=5000)

