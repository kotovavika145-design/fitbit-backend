// ============================================================
// FICHIER : src/app/api/fitbit/heart-rate/route.ts
// RÔLE    : Route dédiée à la fréquence cardiaque
//
// Permet au frontend de récupérer UNIQUEMENT les données FC
// pour mettre à jour uniquement la carte "Fréquence cardiaque"
// sans recharger toutes les données.
//
// Utile pour un polling plus fréquent sur la FC (toutes les 30s)
// vs un polling moins fréquent sur tout (/api/fitbit/data toutes les 60s)
// ============================================================

import { NextRequest, NextResponse } from "next/server";
import { getSession, isSessionValid } from "@/lib/session";
import { getHeartRateIntraday } from "@/lib/fitbitClient";

/**
 * GET /api/fitbit/heart-rate
 *
 * Retourne les données de fréquence cardiaque du jour.
 *
 * Réponse :
 * {
 *   current: number,    // BPM actuel
 *   resting: number,    // FC de repos
 *   history: [{ time, value }],
 *   timestamp: string
 * }
 */
export async function GET(request: NextRequest) {

  // ── Authentification ──
  const session = await getSession();
  if (!isSessionValid(session)) {
    return NextResponse.json(
      { error: "Non authentifié", authUrl: "/api/auth/fitbit" },
      { status: 401 }
    );
  }

  try {
    const data = await getHeartRateIntraday(session.accessToken!);

    // Extraction des données utiles
    const intraday = data["activities-heart-intraday"]?.dataset || [];
    const summary = data["activities-heart"]?.[0]?.value || {};

    // La valeur la plus récente dans les données intraday
    const latestPoint = intraday[intraday.length - 1];

    // Historique des 30 dernières minutes pour le graphique
    const recentHistory = intraday.slice(-30).map((point: any) => ({
      time: point.time?.substring(0, 5),
      value: point.value,
    }));

    return NextResponse.json({
      current: latestPoint?.value || summary.restingHeartRate || 0,
      resting: summary.restingHeartRate || 0,
      zones: summary.heartRateZones || [],
      history: recentHistory,
      timestamp: new Date().toISOString(),
    });

  } catch (error: any) {
    console.error("[HeartRate] Erreur:", error.message);
    return NextResponse.json(
      { error: "Erreur lors de la récupération de la FC", detail: error.message },
      { status: 500 }
    );
  }
}
