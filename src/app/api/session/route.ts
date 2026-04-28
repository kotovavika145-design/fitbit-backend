// ============================================================
// FICHIER : src/app/api/session/route.ts
// RÔLE    : Gestion de la session - statut et déconnexion
//
// Routes disponibles :
//   GET  /api/session → Vérifie si l'utilisateur est connecté
//   DELETE /api/session → Déconnecte l'utilisateur (logout)
//
// Le frontend Vue.js appelle GET /api/session au démarrage
// pour savoir si l'utilisateur a déjà un token Fitbit valide.
// ============================================================

import { NextRequest, NextResponse } from "next/server";
import { getSession, isSessionValid } from "@/lib/session";

/**
 * GET /api/session
 *
 * Vérifie l'état de la session courante.
 * Utile pour le frontend au démarrage : si la session est valide,
 * pas besoin de refaire une authentification Fitbit.
 *
 * Réponse (200) :
 * {
 *   isAuthenticated: boolean,
 *   userId: string | null,
 *   expiresAt: string | null  // ISO date d'expiration du token
 * }
 */
export async function GET(request: NextRequest) {
  const session = await getSession();
  const valid = isSessionValid(session);

  if (!valid) {
    return NextResponse.json({
      isAuthenticated: false,
      userId: null,
      expiresAt: null,
      message: "Aucune session active. Connectez-vous via /api/auth/fitbit",
    });
  }

  return NextResponse.json({
    isAuthenticated: true,
    userId: session.userId,
    // Calcule la date d'expiration lisible
    expiresAt: session.tokenExpiry
      ? new Date(session.tokenExpiry).toISOString()
      : null,
    message: "Session Fitbit active",
  });
}

/**
 * DELETE /api/session
 *
 * Déconnecte l'utilisateur en détruisant la session.
 * À appeler quand l'utilisateur clique sur "Déconnexion" dans Vue.js.
 */
export async function DELETE(request: NextRequest) {
  const session = await getSession();

  // Destruction complète de la session
  session.destroy();

  console.log("[Session] Utilisateur déconnecté");

  return NextResponse.json({
    message: "Déconnexion réussie",
    isAuthenticated: false,
  });
}
