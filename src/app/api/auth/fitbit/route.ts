// ============================================================
// FICHIER : src/app/api/auth/fitbit/route.ts
// RÔLE    : Étape 1 de l'OAuth Fitbit - Redirection vers Fitbit
//
// FLUX OAUTH COMPLET :
//   1. [CE FICHIER] Frontend → GET /api/auth/fitbit
//      → Redirige vers https://fitbit.com/oauth2/authorize
//   2. L'utilisateur se connecte sur Fitbit et autorise l'app
//   3. Fitbit redirige vers /api/fitbit/callback?code=XXX
//   4. [callback/route.ts] On échange le code contre les tokens
//   5. Frontend peut appeler /api/fitbit/data avec les tokens en session
//
// UTILISATION depuis le frontend Vue.js :
//   window.location.href = 'http://localhost:3000/api/auth/fitbit';
// ============================================================

import { NextResponse } from "next/server";
import { buildAuthorizationUrl } from "@/lib/fitbitClient";

/**
 * GET /api/auth/fitbit
 *
 * Génère l'URL d'autorisation Fitbit et redirige l'utilisateur vers elle.
 * L'utilisateur sera invité à :
 *   1. Se connecter à son compte Fitbit
 *   2. Autoriser notre application à accéder à ses données
 */
export async function GET() {
  try {
    // Vérification que les variables d'environnement sont configurées
    if (!process.env.FITBIT_CLIENT_ID) {
      console.error("[Auth] FITBIT_CLIENT_ID manquant dans .env.local");
      return NextResponse.json(
        {
          error: "Configuration manquante",
          message: "FITBIT_CLIENT_ID non défini. Vérifiez votre fichier .env.local",
        },
        { status: 500 }
      );
    }

    // Génération de l'URL d'autorisation OAuth 2.0
    const authorizationUrl = buildAuthorizationUrl();

    console.log("[Auth] Redirection de l'utilisateur vers Fitbit OAuth...");

    // Redirection HTTP 302 vers la page d'autorisation Fitbit
    // L'utilisateur quitte notre application temporairement
    return NextResponse.redirect(authorizationUrl);

  } catch (error) {
    console.error("[Auth] Erreur lors de la génération de l'URL OAuth:", error);
    return NextResponse.json(
      {
        error: "Erreur d'authentification",
        message: "Impossible de démarrer le flux OAuth Fitbit",
      },
      { status: 500 }
    );
  }
}
