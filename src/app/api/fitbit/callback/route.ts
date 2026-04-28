// ============================================================
// FICHIER : src/app/api/fitbit/callback/route.ts
// RÔLE    : Étape 2 de l'OAuth - Réception du code d'autorisation
//
// Cette route est appelée AUTOMATIQUEMENT par Fitbit après que
// l'utilisateur ait autorisé notre application.
//
// Fitbit redirige vers : /api/fitbit/callback?code=AUTHORIZATION_CODE
//
// Ce qu'on fait ici :
//   1. On récupère le "code" dans les query params
//   2. On l'échange contre un "access_token" via l'API Fitbit
//   3. On sauvegarde le token en session (côté serveur, sécurisé)
//   4. On redirige l'utilisateur vers le frontend Vue.js
// ============================================================

import { NextRequest, NextResponse } from "next/server";
import { exchangeCodeForTokens } from "@/lib/fitbitClient";
import { getSession, saveTokensToSession } from "@/lib/session";

/**
 * GET /api/fitbit/callback?code=XXX
 *
 * Route de retour après autorisation Fitbit.
 * Gère l'échange code → tokens et la sauvegarde en session.
 */
export async function GET(request: NextRequest) {
  // ── Extraction des paramètres de l'URL ──
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");   // Code d'autorisation Fitbit
  const error = searchParams.get("error"); // Erreur éventuelle de Fitbit

  // ── Cas d'erreur : l'utilisateur a refusé l'autorisation ──
  if (error) {
    console.error("[Callback] Fitbit a retourné une erreur:", error);
    // Redirige vers le frontend avec une indication d'erreur
    const frontendUrl = process.env.FRONTEND_URL || "http://localhost:5173";
    return NextResponse.redirect(`${frontendUrl}?auth=error&reason=${error}`);
  }

  // ── Validation du code ──
  if (!code) {
    console.error("[Callback] Aucun code d'autorisation reçu");
    return NextResponse.json(
      {
        error: "Code manquant",
        message: "Fitbit n'a pas retourné de code d'autorisation",
      },
      { status: 400 }
    );
  }

  try {
    console.log("[Callback] Code d'autorisation reçu, échange en cours...");

    // ── Échange du code contre les tokens OAuth ──
    // Appel POST vers https://api.fitbit.com/oauth2/token
    const tokens = await exchangeCodeForTokens(code);

    // ── Sauvegarde sécurisée des tokens en session ──
    // Les tokens sont stockés dans un cookie httpOnly chiffré
    // Jamais dans le localStorage ou dans l'URL !
    const session = await getSession();
    await saveTokensToSession(
      session,
      tokens.user_id,       // ID Fitbit de l'utilisateur
      tokens.access_token,  // Pour appeler l'API Fitbit
      tokens.refresh_token, // Pour renouveler automatiquement
      tokens.expires_in     // Durée de validité (généralement 28800s = 8h)
    );

    console.log(`[Callback] Authentification réussie pour l'utilisateur ${tokens.user_id}`);

    // ── Redirection vers le frontend Vue.js ──
    // L'URL frontend avec ?auth=success pour que Vue.js sache que c'est bon
    const frontendUrl = process.env.FRONTEND_URL || "http://localhost:5173";
    return NextResponse.redirect(`${frontendUrl}?auth=success`);

  } catch (error) {
    console.error("[Callback] Erreur lors de l'échange de code:", error);

    // En cas d'erreur, on redirige quand même vers le frontend
    // avec un paramètre d'erreur
    const frontendUrl = process.env.FRONTEND_URL || "http://localhost:5173";
    return NextResponse.redirect(`${frontendUrl}?auth=error&reason=token_exchange_failed`);
  }
}
