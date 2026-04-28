// ============================================================
// FICHIER : src/app/api/fitbit/data/route.ts
// RÔLE    : Route principale - toutes les données agrégées
//
// Cette route est appelée par le frontend Vue.js toutes les
// N secondes pour mettre à jour l'affichage en "temps réel".
//
// Elle :
//   1. Vérifie que l'utilisateur est authentifié (session valide)
//   2. Appelle l'API Fitbit pour récupérer FC + HRV + FR
//   3. Calcule le score de charge mentale objective
//   4. Retourne le tout en JSON au frontend
//
// UTILISATION depuis Vue.js :
//   const response = await fetch('http://localhost:3000/api/fitbit/data', {
//     credentials: 'include' // IMPORTANT : envoie les cookies de session
//   });
// ============================================================

import { NextRequest, NextResponse } from "next/server";
import { getSession, isSessionValid } from "@/lib/session";
import {
  getHeartRateIntraday,
  getHRV,
  getRespiratoryRate,
} from "@/lib/fitbitClient";
import {
  calculateMentalLoad,
  processPhysiologicalData,
} from "@/lib/mentalLoadCalculator";
import { CompleteDataResponse } from "@/types/fitbit";

// ─────────────────────────────────────────
// STOCKAGE EN MÉMOIRE (simplifié)
// ─────────────────────────────────────────

// En production, utilisez Redis ou une base de données
// Ici on garde l'historique et le timestamp de démarrage en mémoire serveur
const sessionRegistry = new Map<string, {
  startTime: number;
  history: any[];
}>();

/**
 * GET /api/fitbit/data
 *
 * Retourne l'ensemble des données physiologiques + score de charge mentale.
 * À appeler depuis le frontend toutes les 60 secondes environ.
 *
 * Réponse en cas de succès (200) :
 * {
 *   physiological: { heartRate, hrv, respiratoryRate, timestamp },
 *   mentalLoad: { score, level, components, history, recommendation },
 *   sessionDuration: number,
 *   dataSource: "live" | "simulated"
 * }
 */
export async function GET(request: NextRequest) {

  // ── Vérification de l'authentification ──
  const session = await getSession();

  if (!isSessionValid(session)) {
    // 401 = l'utilisateur doit se reconnecter
    return NextResponse.json(
      {
        error: "Non authentifié",
        message: "Veuillez vous connecter via /api/auth/fitbit",
        authUrl: "/api/auth/fitbit",
      },
      { status: 401 }
    );
  }

  const userId = session.userId!;
  const accessToken = session.accessToken!;

  // ── Initialisation ou récupération de la session ──
  if (!sessionRegistry.has(userId)) {
    // Première requête pour cet utilisateur → démarre le chrono
    sessionRegistry.set(userId, {
      startTime: Date.now(),
      history: [],
    });
    console.log(`[Data] Nouvelle session démarrée pour ${userId}`);
  }

  const userSession = sessionRegistry.get(userId)!;

  try {
    // ── Appels API Fitbit en parallèle ──
    // Promise.all permet d'appeler les 3 endpoints SIMULTANÉMENT
    // Au lieu de : FC (500ms) + HRV (500ms) + FR (500ms) = 1500ms
    // On obtient : max(FC, HRV, FR) ≈ 500ms
    console.log(`[Data] Récupération des données Fitbit pour ${userId}...`);

    const [heartRateData, hrvData, respiratoryData] = await Promise.all([
      getHeartRateIntraday(accessToken),
      getHRV(accessToken),
      getRespiratoryRate(accessToken),
    ]);

    // ── Traitement des données brutes ──
    // Normalise et structure les données pour le calcul de charge mentale
    const physiologicalData = processPhysiologicalData(
      heartRateData,
      hrvData,
      respiratoryData
    );

    // ── Calcul du score de charge mentale ──
    const mentalLoadScore = calculateMentalLoad(
      physiologicalData,
      userSession.startTime,
      userSession.history
    );

    // Mise à jour de l'historique en mémoire
    userSession.history = mentalLoadScore.history;
    sessionRegistry.set(userId, userSession);

    // ── Calcul de la durée de session ──
    const sessionDurationSeconds = Math.floor(
      (Date.now() - userSession.startTime) / 1000
    );

    // ── Construction de la réponse ──
    const response: CompleteDataResponse = {
      physiological: physiologicalData,
      mentalLoad: mentalLoadScore,
      sessionDuration: sessionDurationSeconds,
      dataSource: "live", // Données réelles de la montre
    };

    console.log(
      `[Data] Score calculé: ${mentalLoadScore.score}/100 (${mentalLoadScore.level}) pour ${userId}`
    );

    return NextResponse.json(response, {
      status: 200,
      headers: {
        // Désactive le cache : on veut des données fraîches à chaque appel
        "Cache-Control": "no-store, no-cache, must-revalidate",
      },
    });

  } catch (error: any) {
    console.error("[Data] Erreur lors de la récupération des données:", error);

    // Gestion spécifique du token expiré
    if (error.message?.includes("FITBIT_TOKEN_EXPIRED")) {
      // Invalide la session pour forcer une re-authentification
      session.isAuthenticated = false;
      await session.save();

      return NextResponse.json(
        {
          error: "Token expiré",
          message: "Votre session Fitbit a expiré. Reconnectez-vous.",
          authUrl: "/api/auth/fitbit",
        },
        { status: 401 }
      );
    }

    // Gestion du rate limit
    if (error.message?.includes("FITBIT_RATE_LIMIT")) {
      return NextResponse.json(
        {
          error: "Limite de requêtes",
          message: "Trop de requêtes vers Fitbit. Réessayez dans quelques minutes.",
          retryAfter: 60,
        },
        { status: 429 }
      );
    }

    return NextResponse.json(
      {
        error: "Erreur serveur",
        message: "Impossible de récupérer les données Fitbit",
        detail: error.message,
      },
      { status: 500 }
    );
  }
}
