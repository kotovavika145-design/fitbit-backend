// ============================================================
// FICHIER : src/app/api/fitbit/hrv/route.ts
// RÔLE    : Route dédiée au HRV (Variabilité Fréquence Cardiaque)
//
// Le HRV (Heart Rate Variability) est l'indicateur le plus
// scientifiquement validé pour mesurer le stress cognitif.
//
// NOTE SUR L'INSPIRE 3 :
//   La Fitbit Inspire 3 mesure le HRV uniquement pendant le sommeil.
//   La valeur disponible via l'API est donc la mesure de la nuit
//   précédente, pas une mesure en temps réel pendant le cours.
//
//   Pour une mesure en temps réel, des appareils comme :
//   - Polar H10 (ceinture thoracique)
//   - Garmin HRM-Pro
//   - Whoop 4.0
//   offrent le HRV en continu.
// ============================================================

import { NextRequest, NextResponse } from "next/server";
import { getSession, isSessionValid } from "@/lib/session";
import { getHRV, getRespiratoryRate } from "@/lib/fitbitClient";

/**
 * GET /api/fitbit/hrv
 *
 * Retourne les données HRV et fréquence respiratoire.
 * Ces deux indicateurs sont liés au système nerveux autonome.
 */
export async function GET(request: NextRequest) {

  const session = await getSession();
  if (!isSessionValid(session)) {
    return NextResponse.json(
      { error: "Non authentifié", authUrl: "/api/auth/fitbit" },
      { status: 401 }
    );
  }

  try {
    // Récupération en parallèle des deux indicateurs
    const [hrvData, respiratoryData] = await Promise.all([
      getHRV(session.accessToken!),
      getRespiratoryRate(session.accessToken!),
    ]);

    // ── Traitement HRV ──
    const hrv = hrvData?.hrv?.[0]?.value;
    const rmssd = hrv?.dailyRms || null;

    // Interprétation scientifique du RMSSD :
    // > 60ms  : Excellente récupération, très faible charge
    // 40-60ms : Bonne récupération, charge faible à modérée
    // 20-40ms : Récupération incomplète, charge modérée
    // < 20ms  : Stress élevé ou fatigue importante
    let hrvInterpretation = "Données non disponibles";
    let hrvLevel: "low" | "moderate" | "high" = "low";

    if (rmssd !== null) {
      if (rmssd > 60) {
        hrvInterpretation = "Excellente récupération";
        hrvLevel = "low";
      } else if (rmssd > 40) {
        hrvInterpretation = "Bonne récupération";
        hrvLevel = "low";
      } else if (rmssd > 20) {
        hrvInterpretation = "Récupération partielle";
        hrvLevel = "moderate";
      } else {
        hrvInterpretation = "Stress ou fatigue détectés";
        hrvLevel = "high";
      }
    }

    // ── Traitement Fréquence Respiratoire ──
    const br = respiratoryData?.br?.[0]?.value;
    const breathingRate = br?.breathingRate || null;

    return NextResponse.json({
      hrv: {
        rmssd: rmssd,                    // Valeur brute en ms
        interpretation: hrvInterpretation,
        level: hrvLevel,
        measuredAt: hrvData?.hrv?.[0]?.dateTime || null, // Date de mesure (nuit précédente)
        note: "Mesure effectuée pendant le sommeil (Inspire 3)",
      },
      respiratoryRate: {
        value: breathingRate,            // Respirations par minute
        measuredAt: respiratoryData?.br?.[0]?.dateTime || null,
        normalRange: "14-20 rpm",        // Plage normale pour un adulte
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error: any) {
    console.error("[HRV] Erreur:", error.message);
    return NextResponse.json(
      { error: "Erreur lors de la récupération du HRV", detail: error.message },
      { status: 500 }
    );
  }
}
