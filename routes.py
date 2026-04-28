from flask import Blueprint, request, jsonify, redirect
"""blueprint : sert à regrouper les routes
request : sert à lire les requetes http
jsonify: retourner du format json
redirect: rediriger vers une url
"""
from datetime import datetime
from extensions import db
from models import (
    User,
    FitbitToken,
    Session,
    SessionParticipant,
    PhysiologicalData,
    NasaTlxResponse,
    MentalLoadResult,
)
""" api fitbit et calculs de la charge mentale """
import fitbit_service
import mental_load_service
"""on crée un groupes de routes nommé api
toutes les routes seront /api/... """
api = Blueprint('api', __name__)

# routes fitbit 
@api.route('/fitbit/authorize/<int:user_id>', methods=['GET'])
def fitbit_authorize(user_id):
    """
    ÉTAPE 1 : Rediriger l'utilisateur vers Fitbit pour l'authentification.
    """
    # Vérifier que l'utilisateur existe
    #s'il n'existe pas , on retourne une erreur
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    # s'il existe, on appelle la fonction get_authorisation_url du module fitbit-service
    #cette fonction prend l'id de l'utilisateur, i'id de l'appli fitbit
    # et l'url de redirection pour rediriger l'utilisateur après l'autorisation
    auth_url = fitbit_service.get_authorization_url(user_id)
    return jsonify({'auth_url': auth_url})


@api.route('/fitbit/callback', methods=['GET'])
def fitbit_callback():
    """
    on récupére ces paramétres à partir de l'url d'authorisation générée"""
    
    code = request.args.get('code')
    user_id = request.args.get('state')
    error = request.args.get('error')

    if error:
        # L'utilisateur a refusé l'accès, on le redirige vers le front
        return redirect(f'http://localhost:5173?fitbit=denied')
        # s'il y a un paramétre manquant, on le signale
    if not code or not user_id:
        return jsonify({'error': 'Paramètres manquants (code ou state)'}), 400

    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({'error': 'user_id invalide dans state'}), 400

    # Échanger le code contre un token
    result = fitbit_service.exchange_code_for_token(code, user_id)

    if result['success']:
        # Rediriger vers le frontend avec succès
        return redirect(f'http://localhost:5173?fitbit=connected&user_id={user_id}')
    else:
        return redirect(f'http://localhost:5173?fitbit=error&msg={result.get("error", "Erreur inconnue")}')


@api.route('/fitbit/status/<int:user_id>', methods=['GET'])
def fitbit_status(user_id):
    """
    Vérifie le statut de connexion Fitbit d'un utilisateur.
    
    GET /api/fitbit/status/1
    → { "connected": true, "fitbit_user_id": "XXXX", "is_expired": false }
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    status = fitbit_service.get_fitbit_status(user_id)
    return jsonify(status)


@api.route('/fitbit/refresh/<int:user_id>', methods=['POST'])
def fitbit_refresh_token(user_id):
    """
    Force le rafraîchissement du token Fitbit.
    
    POST /api/fitbit/refresh/1
    """
    result = fitbit_service.refresh_access_token(user_id)
    if result['success']:
        return jsonify({'message': 'Token rafraîchi avec succès'})
    return jsonify({'error': result.get('error')}), 400


@api.route('/fitbit/disconnect/<int:user_id>', methods=['DELETE'])
def fitbit_disconnect(user_id):
    """
    Déconnecte Fitbit en supprimant les tokens.
    
    DELETE /api/fitbit/disconnect/1
    """
    token = FitbitToken.query.filter_by(user_id=user_id).first()
    if token:
        db.session.delete(token)
        db.session.commit()
    return jsonify({'message': 'Fitbit déconnecté'})


# ═══════════════════════════════════════════════════════════════════
# ROUTES DONNÉES PHYSIOLOGIQUES
# ═══════════════════════════════════════════════════════════════════

@api.route('/fitbit/data/<int:user_id>', methods=['GET'])
def get_physiological_data(user_id):
    """
    Récupère toutes les données physiologiques Fitbit du jour.
    Utilisé pour les mises à jour en temps réel pendant une session.
    
    GET /api/fitbit/data/1
    GET /api/fitbit/data/1?date=2024-01-10
    
    → {
        "heart_rate": 82,
        "resting_heart_rate": 65,
        "hrv": 42,
        "breathing_rate": 17,
        "intraday_hr": [...]
      }
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    date = request.args.get('date', 'today')
    data = fitbit_service.get_all_physiological_data(user_id, date)
    return jsonify(data)


@api.route('/fitbit/heart-rate/<int:user_id>', methods=['GET'])
def get_heart_rate(user_id):
    """
    Récupère uniquement la fréquence cardiaque.
    
    GET /api/fitbit/heart-rate/1
    """
    date = request.args.get('date', 'today')
    data = fitbit_service.get_heart_rate(user_id, date)
    return jsonify(data)


@api.route('/fitbit/hrv/<int:user_id>', methods=['GET'])
def get_hrv(user_id):
    """
    Récupère la variabilité de la fréquence cardiaque (HRV).
    
    GET /api/fitbit/hrv/1
    """
    date = request.args.get('date', 'today')
    data = fitbit_service.get_hrv(user_id, date)
    return jsonify(data)


# ═══════════════════════════════════════════════════════════════════
# ROUTES UTILISATEURS
# ═══════════════════════════════════════════════════════════════════

@api.route('/users', methods=['GET'])
def get_users():
    """
    Liste tous les utilisateurs.
    
    GET /api/users
    GET /api/users?role=student
    """
    role = request.args.get('role')
    #query prépare la requete sql sur la table users
    query = User.query
    if role:
        query = query.filter_by(role=role)
    # exécute la requete et retourne tous les utilisateurs correspondants sous forme d'objets python
    users = query.all()
    # transforme en format json
    return jsonify([u.to_dict() for u in users])


@api.route('/users', methods=['POST'])
def create_user():
    """
    Crée un nouvel utilisateur.
    
    POST /api/users
    Body:
    {
        "email": "etu@etu.u-paris.fr",
        "password": "hash-ou-motdepasse-temporaire",
        "role": "student"
    }
    """
    body = request.get_json() or {}
    email = body.get("email")
    password = body.get("password")
    role = body.get("role","student")

    if not email : 
        return jsonify({"error":"email requis"}),400
    if not password : 
        return jsonify({"error":"password requis"}),400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Cet email existe déjà'}), 409

    user = User(
        email=email,
        password=password,
        role=role,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@api.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """
    Récupère les informations d'un utilisateur.
    
    GET /api/users/1
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    return jsonify(user.to_dict())

# quand le front fait une requete post sur /users, cette méthode sera appelée
@api.route('/users/login', methods=['POST'])
def login_user():
    """
    Connexion simple par email et mot de passe.
    Prototype sans hash pour le moment.
    POST /api/users/login
    Body: { "email": "...", "password": "..." }
    """
    #le corps de la requete est transformé en dictionnaire python
    #si l'utilisateur n'a pas de nom, ça retourne erreur
    body = request.get_json() or {}
    email = body.get("email")
    password = body.get("password")

    if not email:
        return jsonify({"error": "email requis"}), 400
    if not password:
        return jsonify({"error": "password requis"}), 400
    
    #ajout de cet utilisateur
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    if user.password!=password:
        return jsonify({"error": "Mot de passe incorrect"}), 401
    if not user.is_active:
        return jsonify({"error": "Compte inactif"}), 403

    return jsonify(user.to_dict())


# ═══════════════════════════════════════════════════════════════════
# ROUTES SESSIONS
# ═══════════════════════════════════════════════════════════════════

@api.route('/sessions', methods=['POST'])
def create_session():
    """
    Crée une session en BDD sans la démarrer.
    Le démarrage réel (status active + timer) est géré par le socket session_lancee.

    POST /api/sessions
    Body: {
        "created_by": 1,
        "name": "Cours de Bases de Données",
        "group_name": "L2 Groupe A",
        "duration_minutes": 60,
        "device": "Fitbit Inspire 3 (API connectée)",
        "questionnaire_type": "NASA-TLX Raw (début + fin)",
        "participant_ids": [2, 3, 4]
    }
    Retourne la session créée avec son id, que le frontend utilise
    pour l'envoyer ensuite dans le socket session_lancee.
    """
    # création d'une session
    body = request.get_json() or {}
    created_by = body.get("created_by")
    name = body.get("name")

    if not created_by:
        return jsonify({"error": "created_by requis"}), 400
    if not name:
        return jsonify({"error": "name requis"}), 400

    creator = User.query.get(created_by)
    if not creator:
        return jsonify({"error": "Créateur introuvable"}), 404

    session = Session(
        name=name,
        created_by=created_by,
        group_name=body.get("group_name"),
        duration_minutes=body.get("duration_minutes"),
        start_time=None,       # sera défini par le socket session_lancee
        end_time=None,         # sera défini par le socket session_terminee ou le timer
        status="created",      # sera passé à "active" par le socket session_lancee
        device=body.get("device"),
        questionnaire_type=body.get("questionnaire_type"),
    )
    db.session.add(session)
    db.session.flush()

    participant_ids = body.get("participant_ids", [])
    for participant_id in participant_ids:
        participant = User.query.get(participant_id)
        if participant:
            db.session.add(
                SessionParticipant(
                    session_id=session.id,
                    user_id=participant_id,
                    fitbit_connected=False,
                )
            )

    db.session.commit()
    return jsonify(session.to_dict()), 201



@api.route('/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id):
    """
    Récupère les données d'une session.
    
    GET /api/sessions/1
    """
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session introuvable'}), 404
    participants = SessionParticipant.query.filter_by(session_id=session_id).all()

    return jsonify({
        **session.to_dict(),
        "participants": [p.to_dict() for p in participants]
    })

# retourne l'historique des sessions d'un utilisateur
@api.route('/sessions/created_by/<int:user_id>', methods=['GET'])
def get_sessions_created_by(user_id):
    """
    Récupère l'historique des sessions d'un utilisateur.
    
    GET /api/sessions/created_by/1
    """
    sessions = (
        Session.query
        .filter_by(created_by=user_id)
        .order_by(Session.start_time.desc())
        .all()
    )
    return jsonify([s.to_dict() for s in sessions])

@api.route("/sessions/participant/<int:user_id>", methods=["GET"])
def get_sessions_for_participant(user_id):
    participations = (
        SessionParticipant.query
        .filter_by(user_id=user_id)
        .order_by(SessionParticipant.id.desc())
        .all()
    )

    session_ids = [p.session_id for p in participations]
    sessions = Session.query.filter(Session.id.in_(session_ids)).all() if session_ids else []

    return jsonify([s.to_dict() for s in sessions])

@api.route('/sessions/active', methods=['GET'])
def get_active_session():
    session = (
        Session.query
        .filter_by(status='active')
        .order_by(Session.start_time.desc())
        .first()
    )

    if not session:
        return jsonify({'error': 'Aucune session active'}), 404

    return jsonify(session.to_dict())


@api.route('/sessions/<int:session_id>/join', methods=['POST'])
def join_session(session_id):
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session introuvable'}), 404

    body = request.get_json() or {}
    user_id = body.get('user_id')

    if not user_id:
        return jsonify({'error': 'user_id requis'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404

    existing = SessionParticipant.query.filter_by(
        session_id=session_id,
        user_id=user_id
    ).first()

    if existing:
        return jsonify({'message': 'Utilisateur déjà dans la session'})

    participant = SessionParticipant(
        session_id=session_id,
        user_id=user_id,
        fitbit_connected=False
    )
    db.session.add(participant)
    db.session.commit()

    return jsonify(participant.to_dict()), 201

@api.route('/sessions/user/<int:user_id>', methods=['GET'])
def get_user_sessions_compat(user_id):
    participations = (
        SessionParticipant.query
        .filter_by(user_id=user_id)
        .order_by(SessionParticipant.id.desc())
        .all()
    )

    session_ids = [p.session_id for p in participations]
    sessions = Session.query.filter(Session.id.in_(session_ids)).all() if session_ids else []

    results = []
    for s in sessions:
        result = (
            MentalLoadResult.query
            .filter_by(session_id=s.id, user_id=user_id)
            .order_by(MentalLoadResult.created_at.desc())
            .first()
        )

        nasa = (
            NasaTlxResponse.query
            .filter_by(session_id=s.id, user_id=user_id)
            .order_by(NasaTlxResponse.created_at.desc())
            .first()
        )

        results.append({
            'id': s.id,
            'started_at': s.start_time.isoformat() if s.start_time else None,
            'duration_minutes': s.duration_minutes,
            'label': s.name,
            'nasa_tlx_score': result.nasa_score if result else None,
            'mental_load_score': result.global_score if result else None,
            'mental_load_level': result.level if result else None,
        })

    return jsonify(results)

@api.route('/sessions/<int:session_id>/end', methods=['PUT'])
def end_session(session_id):
    """
    Termine une session et calcule le score final de charge mentale.
    
    PUT /api/sessions/1/end
    Body: {
        "user_id": 2,
        "nasa_dimensions": {
            "mental_demand": 70,
            "physical_demand": 20,
            "temporal_demand": 60,
            "performance": 50,
            "effort": 65,
            "frustration": 40
        }
    }
    """
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session introuvable'}), 404

    body = request.get_json() or {}
    user_id = body.get("user_id")
    nasa_dims = body.get('nasa_dimensions', {})

    if not user_id:
        return jsonify({"error": "user_id requis"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    # Marquer la session comme terminée
    session.end_time = datetime.utcnow()
    session.status = "finished"

    # Calculer la durée réelle si non définie
    if session.start_time and not session.duration_minutes:
        delta = session.end_time - session.start_time
        session.duration_minutes = int(delta.total_seconds() / 60)

    # Sauvegarder le NASA-TLX
    nasa_score=None
    if nasa_dims:
        nasa_response = NasaTlxResponse(
            user_id=user_id,
            session_id=session_id,
            mental=nasa_dims.get("mental_demand", 0),
            physical=nasa_dims.get("physical_demand", 0),
            temporal=nasa_dims.get("temporal_demand", 0),
            performance=nasa_dims.get("performance", 0),
            effort=nasa_dims.get("effort", 0),
            frustration=nasa_dims.get("frustration", 0),
            response_time="end",
        )
        db.session.add(nasa_response)
        nasa_score = mental_load_service.calculate_nasa_tlx(nasa_dims)

    # Récupérer les données physiologiques Fitbit
    phys_data = fitbit_service.get_all_physiological_data(user_id)

    # Calculer le score global de charge mentale
    result = mental_load_service.compute_full_mental_load(
        user_id=user_id,
        physiological_data=phys_data,
        nasa_dimensions=nasa_dims
    )

    mental_result = MentalLoadResult(
        user_id=user_id,
        session_id=session_id,
        nasa_score=nasa_score,
        avg_heart_rate=phys_data.get("heart_rate"),
        avg_hrv=phys_data.get("hrv"),
        global_score=result.get("mental_load_score"),
        level=result.get("mental_load_level"),
    )
    db.session.add(mental_result)
    db.session.commit()

    # Ajouter les conseils dans la réponse
    recommendation = mental_load_service.get_recommendation(
        level=result.get("mental_load_level"),
        context="education"
    )

    return jsonify({
        "session_id": session_id,
        "user_id": user_id,
        "mental_load_score": result.get("mental_load_score"),
        "mental_load_level": result.get("mental_load_level"),
        "recommendation": recommendation,
        "calculation_details": result.get("calculation_details", {}),
    })


@api.route('/sessions/<int:session_id>/sample', methods=['POST'])
def add_physiological_sample(session_id):
    """
    Ajoute une mesure physiologique à une session en cours.
    Body: { "user_id": 2 }
    """
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session introuvable'}), 404

    body = request.get_json() or {}
    user_id = body.get("user_id")

    if not user_id:
        return jsonify({"error": "user_id requis"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    phys_data = fitbit_service.get_all_physiological_data(user_id)

    data_row = PhysiologicalData(
        session_id=session_id,
        user_id=user_id,
        heart_rate=phys_data.get('heart_rate'),
        hrv=phys_data.get('hrv'),
        recorded_at=datetime.utcnow(),
    )
    db.session.add(data_row)
    db.session.commit()

    partial_result = mental_load_service.calculate_mental_load_score(
        nasa_score=None,
        hr=phys_data.get('heart_rate'),
        hrv=phys_data.get('hrv'),
        hr_rest=phys_data.get('resting_heart_rate')
    )

    return jsonify({
        **phys_data,
        'mental_load_score': partial_result.get('score'),
        'mental_load_level': partial_result.get('level'),
        'data_id': data_row.id
    })


@api.route('/sessions/<int:session_id>/samples', methods=['GET'])
def get_session_samples(session_id):
    """
    Récupère toutes les mesures d'une session (pour les graphiques).
    
    GET /api/sessions/1/samples
    """
    rows = (
        PhysiologicalData.query
        .filter_by(session_id=session_id)
        .order_by(PhysiologicalData.recorded_at.asc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows])


# ═══════════════════════════════════════════════════════════════════
# ROUTES CHARGE MENTALE
# ═══════════════════════════════════════════════════════════════════

@api.route('/mental-load/compute', methods=['POST'])
def compute_mental_load():
    """
    Calcule la charge mentale à la volée (sans sauvegarder).
    Utile pour des calculs en temps réel.
    
    POST /api/mental-load/compute
    Body: {
        "user_id": 1,
        "nasa_dimensions": { ... },
        "physiological": {         ← optionnel, sinon récupéré depuis Fitbit
            "heart_rate": 82,
            "hrv": 42,
            "resting_heart_rate": 65
        }
    }
    """
    body = request.get_json() or {}
    if not body or not body.get('user_id'):
        return jsonify({'error': 'user_id requis'}), 400

    user_id = body['user_id']

    # Récupérer les données physiologiques
    if body.get('physiological'):
        phys_data = body['physiological']
    else:
        phys_data = fitbit_service.get_all_physiological_data(user_id)

    result = mental_load_service.compute_full_mental_load(
        user_id=user_id,
        physiological_data=phys_data,
        nasa_dimensions=body.get('nasa_dimensions', {})
    )

    # Ajouter les conseils
    context = body.get('context', 'education')
    if result.get('mental_load_level'):
        result['recommendation'] = mental_load_service.get_recommendation(
            result['mental_load_level'], context
        )

    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════
# ROUTE DE SANTÉ (Health Check)
# ═══════════════════════════════════════════════════════════════════

@api.route('/health', methods=['GET'])
def health_check():
    """
    Vérifie que le backend fonctionne.
    
    GET /api/health
    → { "status": "ok", "timestamp": "..." }
    """
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })
