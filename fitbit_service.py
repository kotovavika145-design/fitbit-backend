# fitbit_service.py
# Gère toute la logique de connexion OAuth 2.0 avec Fitbit
# et la récupération des données physiologiques.
#importer le système d'exploitation
import os
# pour encoder le client secret et le client id
import base64
# pour faire des requetes http
import requests
#savoir quand un token expire et calculer une date future
from datetime import datetime, timedelta
from extensions import db
from models import FitbitToken, User

# URL commune de callback
REDIRECT_URI = os.getenv(
    'FITBIT_REDIRECT_URI',
    'http://localhost:5000/api/fitbit/callback'
)

#obtenus après la création de l'application développeur
FITBIT_AUTH_URL = 'https://www.fitbit.com/oauth2/authorize'
FITBIT_TOKEN_URL = 'https://api.fitbit.com/oauth2/token'
FITBIT_API_BASE = 'https://api.fitbit.com'

# Scopes demandés : fréquence cardiaque, activité, profil, respiration, HRV
SCOPES = 'heartrate activity profile respiratory_rate'

# Mapping users de la BDD -> credentials Fitbit
USER1_DB_ID = int(os.getenv('FITBIT_USER1_DB_ID', '1'))
USER2_DB_ID = int(os.getenv('FITBIT_USER2_DB_ID', '2'))

def get_credentials(user_id):
    """
    Retourne le (client_id, client_secret) à utiliser pour cet utilisateur.

    Logique actuelle :
    - user_id == FITBIT_USER1_DB_ID -> FITBIT_CLIENT_ID_1 / FITBIT_CLIENT_SECRET_1
    - user_id == FITBIT_USER2_DB_ID -> FITBIT_CLIENT_ID_2 / FITBIT_CLIENT_SECRET_2

    Fallback :
    - si FITBIT_CLIENT_ID / FITBIT_CLIENT_SECRET existent, on peut les utiliser
      comme configuration par défaut
    """
    if user_id == USER1_DB_ID:
        client_id = os.getenv('FITBIT_CLIENT_ID_1')
        client_secret = os.getenv('FITBIT_CLIENT_SECRET_1')
    elif user_id == USER2_DB_ID:
        client_id = os.getenv('FITBIT_CLIENT_ID_2')
        client_secret = os.getenv('FITBIT_CLIENT_SECRET_2')
    else:
        # fallback éventuel si tu veux tester avec une seule app Fitbit
        client_id = os.getenv('FITBIT_CLIENT_ID')
        client_secret = os.getenv('FITBIT_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError(
                f"Aucune app Fitbit configurée pour user_id={user_id}. "
                "Vérifie FITBIT_USER1_DB_ID / FITBIT_USER2_DB_ID "
                "ou ajoute FITBIT_CLIENT_ID / FITBIT_CLIENT_SECRET par défaut."
            )

    if not client_id or not client_secret:
        raise ValueError(
            f"CLIENT_ID ou CLIENT_SECRET manquant dans .env pour user_id={user_id}"
        )

    return client_id, client_secret

# ─── ÉTAPE 1 : Construire l'URL d'autorisation ──────────────────────────────
def get_authorization_url(user_id):
    """
    Construit l'URL de redirection vers Fitbit pour l'authentification OAuth 2.0.
    L'utilisateur sera redirigé vers cette URL pour autoriser l'accès.
    """
    #création d'un dictionnaire avec tous les parametres dont on a besoin
    #response-type indique à fitbit qu'on demande un code temporaire
    #client-id permet de savoir quelle application demande les données
    #redirection-uri indique où rediriger l'utilisateur après avoir accepté le partage de ses données
    #scope permet d'indiquer ce qu'on veut récupérer ( fréquence cardique..)
    client_id, _ = get_credentials(user_id)
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'state': str(user_id)   # On passe l'user_id dans state pour le retrouver au callback
    }

    # Construire la query string manuellement pour contrôler l'encodage
    #requests.util.quote(..) permet d'encoder les valeurs v pour qu'elles soient valides dans une url
    #'&'.join(..) permet de rassembler tous ces parametres sur une meme ligne
    query = '&'.join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    #exemple de l'url générée
    #https://www.fitbit.com/oauth2/authorize?response_type=code&client_id=23TTNJ&redirect_uri=ht
    url = f"{FITBIT_AUTH_URL}?{query}"
    return url


# ─── ÉTAPE 4 : Échanger le code contre un token ─────────────────────────────
def exchange_code_for_token(code, user_id):
    """
    Échange le code d'autorisation OAuth contre un access_token et refresh_token.
    Stocke les tokens en base de données.

    Algorithme :
    1. Encoder client_id:client_secret en Base64
    2. Envoyer POST à Fitbit /oauth2/token
    3. Recevoir access_token, refresh_token, expires_in
    4. Sauvegarder en base de données
    5. Retourner succès/erreur
    """

    try:
        client_id, client_secret = get_credentials(user_id)
    except ValueError as e:
        return {'success': False, 'error': str(e)}
    # Encoder les credentials en Base64 pour l'en-tête Authorization
    # credentials combine le client id et le client secret
    credentials = f"{client_id}:{client_secret}"
    #credentials.encode() permet de transformer le texte en bytes
    #decode() permet de le retransformer en string
    encoded = base64.b64encode(credentials.encode()).decode()

    headers = {
         # 'Authorization' montre a fitbit qu'on est l'application autorisée
         #'Content-type' dit à fitbit  dans quel format on envoie les données
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    #corps de la requete Post qu'on envoie
    #on utilise le client-id
    #grant-type indique qu'on utilise le code temporaire pour récupérer le token
    # redirect-uri: fitbit vérifie que c'est le meme qu'au moment de l'autorisation
    #code : c'est le code temporaire reçu 

    data = {
        'client_id': client_id,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'code': code
    }

    try:
        response = requests.post(FITBIT_TOKEN_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()

        # on transforme le token envoyé en format dictionnaire
        token_data = response.json()

        # Calculer la date d'expiration (expires_in est en secondes, généralement 28800 = 8h)
        expires_in = token_data.get('expires_in', 28800)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Sauvegarder ou mettre à jour le token en base
        existing_token = FitbitToken.query.filter_by(user_id=user_id).first()

        if existing_token:
            existing_token.access_token = token_data['access_token']
            existing_token.refresh_token = token_data['refresh_token']
            existing_token.expires_at = expires_at
            existing_token.fitbit_user_id = token_data.get('user_id')
            existing_token.updated_at = datetime.utcnow()
        else:
            new_token = FitbitToken(
                user_id=user_id,
                fitbit_user_id=token_data.get('user_id'),
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                expires_at=expires_at
            )
            db.session.add(new_token)

        db.session.commit()
        return {'success': True, 'fitbit_user_id': token_data.get('user_id')}

    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}


# ─── ÉTAPE 7 : Rafraîchir le token expiré ───────────────────────────────────
def refresh_access_token(user_id):
    """
    Utilise le refresh_token pour obtenir un nouveau access_token.
    Met à jour la base de données avec les nouveaux tokens.
    """
    #ici on interroge la bdd pour trouver le fitbit token associé à cet utilisateur
    token_record = FitbitToken.query.filter_by(user_id=user_id).first()
    if not token_record:
        return {'success': False, 'error': 'Aucun token trouvé pour cet utilisateur'}
    #on encode le token avec la base64
    try:
        client_id, client_secret = get_credentials(user_id)
    except ValueError as e:
        return {'success': False, 'error': str(e)}

    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    # en-tete fitbit
    headers = {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    # grant-type montre qu'on demande un refresh token
    #refresh-token : on y met le token qu'on avait
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': token_record.refresh_token,
        'client_id': client_id
    }

    try:
        response = requests.post(FITBIT_TOKEN_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()

        expires_in = token_data.get('expires_in', 28800)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Mettre à jour en base
        token_record.access_token = token_data['access_token']
        token_record.refresh_token = token_data.get('refresh_token', token_record.refresh_token)
        token_record.expires_at = expires_at
        token_record.updated_at = datetime.utcnow()
        db.session.commit()

        return {'success': True}

    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}


# ─── Utilitaire : Obtenir un token valide (avec auto-refresh) ────────────────
def get_valid_token(user_id):
    """
    Retourne un access_token valide pour l'utilisateur.
    Rafraîchit automatiquement si le token est expiré.
    """
    #on cherche le token dans la db et si on n'en trouve pas on retourne none
    token_record = FitbitToken.query.filter_by(user_id=user_id).first()
    if not token_record:
        return None
    #si le token a expiré, on appelle la fonction précédente pour en demander un nouveau
    if token_record.is_expired():
        result = refresh_access_token(user_id)
        if not result['success']:
            return None
        #si le chargement a réussi, on recharge le token en base
        token_record = FitbitToken.query.filter_by(user_id=user_id).first()

    return token_record.access_token


# ─── ÉTAPE 6 : Récupérer la fréquence cardiaque ─────────────────────────────
def get_heart_rate(user_id, date='today'):
    """
    Récupère la fréquence cardiaque depuis l'API Fitbit.
    GET https://api.fitbit.com/1/user/-/activities/heart/date/{date}/1d.json

    Retourne :
    - resting_heart_rate : fréquence cardiaque au repos
    - intraday_data : mesures intrajournalières (si disponible)
    """
    #on appelle la fonction get_valid_token() qu'on a définie avant
    access_token = get_valid_token(user_id)
    if not access_token:
        return {'error': 'Token Fitbit non disponible. Veuillez reconnecter votre Fitbit.'}
    #on envoie un jeton d'accès pour autoriser la requete
    #on met l'access token autorisé avant
    headers = {'Authorization': f'Bearer {access_token}'}
    #on construit l'url complete pour récupérer la fréqence cardiaque
    url = f"{FITBIT_API_BASE}/1/user/-/activities/heart/date/{date}/1d/1min.json"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        #on transforme les données ontenues en format json
        data = response.json()

        activities = data.get('activities-heart', [])
        if not activities:
            return {'error': 'Aucune donnée cardiaque disponible'}
        #retourne la liste des mesures du jour, si elle est vide, elle ne retourne rien
        #si fitbit n'a rien récupéré ce jour-là
        day_data = activities[0].get('value', {})
        resting_hr = day_data.get('restingHeartRate', None)

        # Données intrajournalières (mesures minute par minute)
        intraday = data.get('activities-heart-intraday', {})
        dataset = intraday.get('dataset', [])

        # Calculer la FC moyenne à partir des données intrajournalières
        avg_hr = None
        if dataset:
            values = [d['value'] for d in dataset if d.get('value', 0) > 0]
            avg_hr = round(sum(values) / len(values), 1) if values else None

        return {
            'resting_heart_rate': resting_hr,
            'avg_heart_rate': avg_hr,
            'intraday_data': dataset[-60:] if dataset else []  # 60 dernières minutes
        }
    # gérer les erreurs http
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            # Token invalide, essayer de rafraîchir
            refresh_access_token(user_id)
            return {'error': 'Token expiré, veuillez réessayer'}
        return {'error': f"Erreur API Fitbit: {e.response.status_code if e.response else 'HTTP'}"}
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


# ─── Récupérer la variabilité de la fréquence cardiaque (HRV) ───────────────
def get_hrv(user_id, date='today'):
    """
    Récupère le HRV (Heart Rate Variability) depuis l'API Fitbit.
    GET https://api.fitbit.com/1/user/-/hrv/date/{date}.json

    Note : La Fitbit Inspire 3 supporte le HRV en mode sommeil.
    """
    access_token = get_valid_token(user_id)
    if not access_token:
        return {'error': 'Token Fitbit non disponible'}

    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"{FITBIT_API_BASE}/1/user/-/hrv/date/{date}.json"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        #récupérer l'hrv du jour
        hrv_data = data.get('hrv', [])
        if not hrv_data:
            return {'hrv': None, 'message': 'Aucune donnée HRV disponible pour aujourd\'hui'}

        # Prendre la valeur rmssd (Root Mean Square of Successive Differences)
        daily = hrv_data[0].get('value', {})
        rmssd = daily.get('dailyRmssd', None)
        deep_rmssd = daily.get('deepRmssd', None)

        return {
            'hrv': rmssd,
            'deep_hrv': deep_rmssd,
            'date': hrv_data[0].get('dateTime')
        }

    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


# ─── Récupérer la fréquence respiratoire ────────────────────────────────────
def get_breathing_rate(user_id, date='today'):
    """
    Récupère la fréquence respiratoire depuis l'API Fitbit.
    GET https://api.fitbit.com/1/user/-/br/date/{date}.json
    """
    access_token = get_valid_token(user_id)
    if not access_token:
        return {'error': 'Token Fitbit non disponible'}

    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"{FITBIT_API_BASE}/1/user/-/br/date/{date}.json"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        br_data = data.get('br', [])
        if not br_data:
            return {'breathing_rate': None, 'message': 'Aucune donnée respiratoire disponible'}

        value = br_data[0].get('value', {})
        breathing_rate = value.get('breathingRate', None)

        return {
            'breathing_rate': breathing_rate,
            'date': br_data[0].get('dateTime')
        }

    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


# ─── Récupérer toutes les données physiologiques en une fois ─────────────────
def get_all_physiological_data(user_id, date='today'):
    """
    Agrège toutes les données physiologiques Fitbit pour un utilisateur.
    Utilisé pour les mesures en temps réel pendant une session.
    """
    #appel des fonctions précédentes
    hr_data = get_heart_rate(user_id, date)
    hrv_data = get_hrv(user_id, date)
    br_data = get_breathing_rate(user_id, date)

    return {
        'heart_rate': hr_data.get('avg_heart_rate'),
        'resting_heart_rate': hr_data.get('resting_heart_rate'),
        'hrv': hrv_data.get('hrv'),
        'breathing_rate': br_data.get('breathing_rate'),
        'intraday_hr': hr_data.get('intraday_data', []),
        'errors': {
            'hr': hr_data.get('error'),
            'hrv': hrv_data.get('error'),
            'br': br_data.get('error')
        }
    }


# ─── Vérifier le statut de connexion Fitbit ─────────────────────────────────
def get_fitbit_status(user_id):
    """
    Retourne le statut de connexion Fitbit pour un utilisateur.
    """
    token_record = FitbitToken.query.filter_by(user_id=user_id).first()
    if not token_record:
        return {'connected': False}

    return {
        'connected': True,
        'fitbit_user_id': token_record.fitbit_user_id,
        'expires_at': token_record.expires_at.isoformat(),
        'is_expired': token_record.is_expired()
    }