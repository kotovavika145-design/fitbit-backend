# mental_load_service.py
# Calcule la charge mentale en combinant NASA-TLX et données physiologiques Fitbit.
#
# Formule finale :
#   score_global = 0.5 × NASA-TLX + 0.3 × HR_normalisé + 0.2 × HRV_normalisé
#
# Classification :
#   < 40  → Charge faible
#   40–70 → Charge modérée
#   > 70  → Charge élevée


# ─── Constantes de normalisation ────────────────────────────────────────────
# Valeurs de référence physiologiques (adulte sain au repos, activité légère)
HR_REST_DEFAULT = 65     # FC repos par défaut (bpm)
HR_MAX_DEFAULT = 185     # FC max estimée (bpm)
HRV_MIN_DEFAULT = 20     # HRV minimale (ms) → stress maximal
HRV_MAX_DEFAULT = 80     # HRV maximale (ms) → très relaxé


# ─── NORMALISATION ──────────────────────────────────────────────────────────

def normalize_heart_rate(hr, hr_rest=HR_REST_DEFAULT, hr_max=HR_MAX_DEFAULT):
    """
    Normalise la fréquence cardiaque sur une échelle 0–100.
    Une FC proche du max → score élevé (stress physiologique fort).

    Formule :
        score_hr = (HR - HR_rest) / (HR_max - HR_rest) × 100

    Args:
        hr       : Fréquence cardiaque mesurée (bpm)
        hr_rest  : Fréquence cardiaque au repos (bpm)
        hr_max   : Fréquence cardiaque maximale estimée (bpm)

    Returns:
        float entre 0 et 100
    """
    if hr is None:
        return None

    score = (hr - hr_rest) / (hr_max - hr_rest) * 100

    # Clamp entre 0 et 100
    return max(0.0, min(100.0, round(score, 2)))


def normalize_hrv(hrv, hrv_min=HRV_MIN_DEFAULT, hrv_max=HRV_MAX_DEFAULT):
    """
    Normalise le HRV sur une échelle 0–100.
    HRV basse = stress élevé → score élevé.
    HRV haute = relaxé → score faible.

    Formule (inverse) :
        score_hrv = (HRV_max - HRV) / (HRV_max - HRV_min) × 100

    Args:
        hrv     : HRV mesurée (ms)
        hrv_min : HRV minimale de référence (ms)
        hrv_max : HRV maximale de référence (ms)

    Returns:
        float entre 0 et 100
    """
    if hrv is None:
        return None

    score = (hrv_max - hrv) / (hrv_max - hrv_min) * 100

    return max(0.0, min(100.0, round(score, 2)))


# ─── CALCUL NASA-TLX ────────────────────────────────────────────────────────

def calculate_nasa_tlx(dimensions):
    """
    Calcule le score NASA-TLX Raw à partir des 6 dimensions.
    Chaque dimension est notée de 0 à 100.

    Dimensions :
        - mental_demand     : Demande mentale
        - physical_demand   : Demande physique
        - temporal_demand   : Demande temporelle
        - performance       : Performance perçue
        - effort            : Effort
        - frustration       : Frustration

    Args:
        dimensions : dict avec les 6 scores (0–100)

    Returns:
        float : score moyen NASA-TLX (0–100)
    """
    required = ['mental_demand', 'physical_demand', 'temporal_demand',
                'performance', 'effort', 'frustration']

    values = []
    for key in required:
        val = dimensions.get(key)
        if val is not None:
            values.append(float(val))

    if not values:
        return None

    return round(sum(values) / len(values), 2)


# ─── CALCUL SCORE GLOBAL ────────────────────────────────────────────────────

def calculate_mental_load_score(nasa_score, hr, hrv,
                                 hr_rest=HR_REST_DEFAULT,
                                 hr_max=HR_MAX_DEFAULT,
                                 hrv_min=HRV_MIN_DEFAULT,
                                 hrv_max=HRV_MAX_DEFAULT):
    """
    Calcule le score global de charge mentale.

    Formule :
        score_global = 0.5 × NASA + 0.3 × score_HR + 0.2 × score_HRV

    Si des données physiologiques sont absentes, les poids sont redistribués.

    Args:
        nasa_score : Score NASA-TLX (0–100), peut être None
        hr         : Fréquence cardiaque (bpm), peut être None
        hrv        : HRV (ms), peut être None
        hr_rest    : FC repos de l'utilisateur
        hr_max     : FC max estimée
        hrv_min    : HRV minimale de référence
        hrv_max    : HRV maximale de référence

    Returns:
        dict avec score, niveau et détails de calcul
    """
    score_nasa = nasa_score
    score_hr = normalize_heart_rate(hr, hr_rest, hr_max)
    score_hrv = normalize_hrv(hrv, hrv_min, hrv_max)

    # Calculer les poids disponibles
    components = []
    total_weight = 0

    if score_nasa is not None:
        components.append(('nasa', score_nasa, 0.5))
        total_weight += 0.5
    if score_hr is not None:
        components.append(('hr', score_hr, 0.3))
        total_weight += 0.3
    if score_hrv is not None:
        components.append(('hrv', score_hrv, 0.2))
        total_weight += 0.2

    if not components:
        return {
            'score': None,
            'level': None,
            'error': 'Aucune donnée disponible pour calculer la charge mentale'
        }

    # Si tous les composants sont disponibles → formule standard
    if total_weight == 1.0:
        score_global = (0.5 * score_nasa + 0.3 * score_hr + 0.2 * score_hrv)
    else:
        # Redistribuer les poids proportionnellement
        score_global = sum((w / total_weight) * s for _, s, w in components)

    score_global = round(score_global, 2)

    return {
        'score': score_global,
        'level': classify_mental_load(score_global),
        'details': {
            'nasa_score': score_nasa,
            'hr_normalized': score_hr,
            'hrv_normalized': score_hrv,
            'weights_used': {c[0]: c[2] for c in components}
        }
    }


# ─── CLASSIFICATION ─────────────────────────────────────────────────────────

def classify_mental_load(score):
    """
    Classifie le score de charge mentale en 3 niveaux.

    Algorithme :
        si score < 40   → 'low'      (charge faible)
        si 40 ≤ score ≤ 70 → 'moderate' (charge modérée)
        si score > 70   → 'high'     (charge élevée)
    """
    if score is None:
        return None
    if score < 40:
        return 'low'
    elif score <= 70:
        return 'moderate'
    else:
        return 'high'


# ─── POINT D'ENTRÉE PRINCIPAL ────────────────────────────────────────────────

def compute_full_mental_load(user_id, physiological_data, nasa_dimensions):
    """
    Calcule la charge mentale complète à partir des données Fitbit + NASA-TLX.

    Algorithme complet :
    1. Récupérer données physiologiques (HR, HRV)
    2. Récupérer score NASA-TLX
    3. Normaliser HR
    4. Normaliser HRV
    5. Calculer score global
    6. Classifier la charge mentale
    7. Retourner le résultat complet

    Args:
        user_id             : ID de l'utilisateur
        physiological_data  : dict { heart_rate, hrv, resting_heart_rate, breathing_rate }
        nasa_dimensions     : dict des 6 dimensions NASA-TLX (0–100 chacune)

    Returns:
        dict avec score global, niveau et toutes les données détaillées
    """
    hr = physiological_data.get('heart_rate')
    hrv = physiological_data.get('hrv')
    hr_rest = physiological_data.get('resting_heart_rate', HR_REST_DEFAULT)

    # Calculer le score NASA-TLX
    nasa_score = calculate_nasa_tlx(nasa_dimensions) if nasa_dimensions else None

    # Calculer le score global
    result = calculate_mental_load_score(
        nasa_score=nasa_score,
        hr=hr,
        hrv=hrv,
        hr_rest=hr_rest if hr_rest else HR_REST_DEFAULT
    )

    return {
        'user_id': user_id,
        'mental_load_score': result['score'],
        'mental_load_level': result['level'],
        'nasa_tlx_score': nasa_score,
        'physiological': {
            'heart_rate': hr,
            'resting_heart_rate': hr_rest,
            'hrv': hrv,
            'breathing_rate': physiological_data.get('breathing_rate')
        },
        'calculation_details': result.get('details', {})
    }


# ─── CONSEILS ────────────────────────────────────────────────────────────────

def get_recommendation(level, context='education'):
    """
    Retourne un conseil adapté au niveau de charge mentale et au contexte.

    Args:
        level   : 'low' | 'moderate' | 'high'
        context : 'education' | 'aviation'
    """
    recommendations = {
        'education': {
            'low': {
                'icon': '✅',
                'message': 'Charge faible. Vous êtes dans un état optimal pour l\'apprentissage.',
                'action': None
            },
            'moderate': {
                'icon': '⚠️',
                'message': 'Charge modérée. Pensez à prévoir une pause lors de votre prochaine séance longue.',
                'action': 'Pause de 5 minutes recommandée'
            },
            'high': {
                'icon': '🔴',
                'message': 'Charge élevée. Une pause est fortement recommandée pour préserver vos capacités cognitives.',
                'action': 'Arrêt immédiat et pause de 15 minutes'
            }
        }
    }
        

    ctx = recommendations.get(context, recommendations['education'])
    return ctx.get(level, ctx['moderate'])