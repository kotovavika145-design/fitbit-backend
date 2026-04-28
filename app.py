import os
import threading
from datetime import datetime
from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from extensions import db
from models import User, FitbitToken, Session, PhysiologicalData, SessionParticipant

# ─── ÉTAPE 1 : Charger les variables d'environnement ────────────────────────
load_dotenv()

# ─── ÉTAPE 2 : Créer l'application Flask ────────────────────────────────────
app = Flask(__name__)

# ─── ÉTAPE 3 : Configurer la base de données ────────────────────────────────
# DATABASE_URL est défini dans le fichier .env
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/mental_load_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

# ─── ÉTAPE 4 : Activer CORS ──────────────────────────────────────────────────
# Autorise les requêtes venant du frontend Vue.js (port 5173 par défaut avec Vite)
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:5173",   # Vite dev server
            "http://localhost:3000",   # Autre port possible
            "http://localhost",
            "http://127.0.0.1:5173"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ─── ÉTAPE 4bis : Initialiser SocketIO ───────────────────────────────────────
# cors_allowed_origins="*" autorise le frontend Vue.js à se connecter en WebSocket
socketio = SocketIO(app, cors_allowed_origins="*")

# ─── ÉTAPE 5 : Initialiser SQLAlchemy ───────────────────────────────────────
db.init_app(app)

# ─── ÉTAPE 6 & 7 : Créer les tables et enregistrer les routes ───────────────
with app.app_context():
    # Import des modèles pour que SQLAlchemy les connaisse avant create_all()
    from models import User, FitbitToken, Session, PhysiologicalData

    # Créer toutes les tables si elles n'existent pas encore
    db.create_all()
    print("Tables créées (ou déjà existantes)")

    # Enregistrer le Blueprint des routes avec le préfixe /api
    from routes import api
    app.register_blueprint(api, url_prefix='/api')
    print("✅ Routes enregistrées sous /api")


# ─── GESTIONNAIRE DE TIMERS ───────────────────────────────────────────────────
# Dictionnaire qui stocke les timers actifs : { session_id: threading.Timer }
# Permet d'annuler un timer si le prof termine la session manuellement avant
# que le temps soit écoulé
_session_timers = {}


def _terminer_session_automatique(session_id, nom_session):
    """
    Appelé automatiquement par le timer quand la durée de la session est écoulée.
    - Met à jour le statut en BDD → "finished"
    - Émet 'aller_questionnaire' à tous les clients connectés via SocketIO
    - Émet 'session_terminee_serveur' à l'enseignant pour mettre à jour son UI
    - Supprime le timer du dictionnaire
    """
    print(f"⏰ Timer écoulé pour la session {session_id} ({nom_session})")

    # On a besoin du contexte applicatif Flask pour accéder à la BDD
    with app.app_context():
        session = Session.query.get(session_id)

        # Vérifier que la session existe et est encore active
        # (elle pourrait avoir été terminée manuellement entre-temps)
        if session and session.status == 'active':
            session.status = 'finished'
            session.end_time = datetime.utcnow()
            db.session.commit()
            print(f"✅ Session {session_id} marquée 'finished' en BDD")

            # Notifier tous les étudiants → redirection vers le questionnaire
            socketio.emit('aller_questionnaire', {})

            # Notifier l'enseignant → mise à jour de son UI (sessionTerminee = true)
            socketio.emit('session_terminee_serveur', {
                'session_id': session_id,
                'nom': nom_session
            })
        else:
            print(f"ℹ️ Session {session_id} déjà terminée, timer ignoré")

    # Nettoyage du timer dans le dictionnaire
    _session_timers.pop(session_id, None)


def _demarrer_timer_session(session_id, duree_secondes, nom_session):
    """
    Lance un threading.Timer qui appellera _terminer_session_automatique
    après duree_secondes secondes.
    Si un timer existait déjà pour cette session, il est annulé d'abord.
    """
    # Annuler le timer existant si on relance la même session
    _annuler_timer_session(session_id)

    timer = threading.Timer(
        duree_secondes,
        _terminer_session_automatique,
        args=[session_id, nom_session]
    )
    # daemon=True : le timer ne bloque pas l'arrêt du serveur
    timer.daemon = True
    timer.start()

    # Stocker le timer pour pouvoir l'annuler plus tard
    _session_timers[session_id] = timer
    print(f"⏱️ Timer démarré pour session {session_id} : {duree_secondes}s ({duree_secondes//60}min)")


def _annuler_timer_session(session_id):
    """
    Annule le timer d'une session si il existe.
    Appelé quand le prof termine la session manuellement.
    """
    timer = _session_timers.pop(session_id, None)
    if timer:
        timer.cancel()
        print(f"🛑 Timer annulé pour session {session_id}")


# ─── ÉTAPE 7bis : Événements WebSocket ───────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    """Appelé quand un client (étudiant ou enseignant) se connecte."""
    print(f'Client connecté : {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    """Appelé quand un client se déconnecte."""
    print(f'Client déconnecté : {request.sid}')

@socketio.on('session_lancee')
def handle_session_lancee(data):
    """
    L'enseignant lance une session.
    data = { 'session_id': 1, 'duree': '1h00', 'dureeSecondes': 3600, 'nom': '...' }

    Le backend :
    1. Met le statut de la session à 'active' en BDD
    2. Démarre un timer serveur qui terminera automatiquement la session
    3. Diffuse 'session_demarree' à tous les étudiants connectés
    """
    session_id     = data.get('session_id')
    duree_secondes = data.get('dureeSecondes', 3600)
    nom_session    = data.get('nom', 'Session')
    duree_affichee = data.get('duree', '1h00')

    # ── 1. Mettre à jour le statut en BDD ──────────────────────────────────
    if session_id:
        with app.app_context():
            session = Session.query.get(session_id)
            if session:
                session.status     = 'active'
                session.start_time = datetime.utcnow()
                db.session.commit()
                print(f"✅ Session {session_id} passée à 'active' en BDD")

        # ── 2. Démarrer le timer serveur ────────────────────────────────────
        _demarrer_timer_session(session_id, duree_secondes, nom_session)
    else:
        print("⚠️ session_lancee reçu sans session_id — timer non démarré")

    # ── 3. Diffuser aux étudiants ───────────────────────────────────────────
    emit('session_demarree', {
        'session_id':    session_id,
        'duree':         duree_affichee,
        'dureeSecondes': duree_secondes,
        'nom':           nom_session
    }, broadcast=True)


@socketio.on('session_terminee')
def handle_session_terminee(data):
    """
    Le prof termine la session manuellement (avant la fin du chrono).
    data = { 'session_id': 1, 'nom': '...' }

    Le backend :
    1. Annule le timer automatique s'il est encore en cours
    2. Met le statut à 'finished' en BDD
    3. Redirige tous les étudiants vers le questionnaire
    """
    session_id  = data.get('session_id')
    nom_session = data.get('nom', 'Session')

    # ── 1. Annuler le timer automatique ────────────────────────────────────
    if session_id:
        _annuler_timer_session(session_id)

        # ── 2. Mettre à jour la BDD ─────────────────────────────────────────
        with app.app_context():
            session = Session.query.get(session_id)
            if session and session.status == 'active':
                session.status   = 'finished'
                session.end_time = datetime.utcnow()
                db.session.commit()
                print(f"✅ Session {session_id} terminée manuellement → 'finished' en BDD")
    else:
        print("⚠️ session_terminee reçu sans session_id")

    # ── 3. Rediriger les étudiants vers le questionnaire ───────────────────
    emit('aller_questionnaire', {}, broadcast=True)


@socketio.on('score_soumis')
def handle_score_soumis(data):
    """
    Un étudiant soumet son score NASA-TLX.
    data = { 'username': '...', 'score': '...', 'niveau': '...' }
    → on notifie l'enseignant pour rafraîchir la vue groupe
    """
    emit('nouveau_score', data, broadcast=True)


# ─── ÉTAPE 8 : Lancer le serveur ────────────────────────────────────────────
if __name__ == '__main__':
    print("🚀 Démarrage du serveur Flask...")
    print(f"   Base de données : {os.getenv('DATABASE_URL', 'non configurée')}")
    print(f"   Fitbit Client ID : {os.getenv('FITBIT_CLIENT_ID', 'non configuré')}")
    print(f"   Serveur disponible sur : http://localhost:5000")
    # socketio.run remplace app.run pour activer le support WebSocket
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True   # À mettre False en production
    )
