/**
 * Constant-time authentication utility to prevent timing attacks.
 */

export async function verifyBearerToken(
  authHeader: string | null,
  expectedSecret: string | undefined
): Promise<boolean> {
  if (!authHeader || !expectedSecret || typeof expectedSecret !== "string") {
    return false;
  }

  const parts = authHeader.trim().split(" ");
  if (parts.length !== 2 || parts[0].toLowerCase() !== "bearer") {
    return false;
  }

  const providedToken = parts[1];
  if (!providedToken || providedToken.length === 0) {
    return false;
  }

  // Hash both strings to 256-bit digests and compare using timingSafeEqual
  const enc = new TextEncoder();
  const providedHash = await crypto.subtle.digest("SHA-256", enc.encode(providedToken));
  const expectedHash = await crypto.subtle.digest("SHA-256", enc.encode(expectedSecret));

  const pBuf = new Uint8Array(providedHash);
  const eBuf = new Uint8Array(expectedHash);

  if (pBuf.length !== eBuf.length) {
    return false;
  }

  // Bitwise XOR comparison
  let diff = 0;
  for (let i = 0; i < pBuf.length; i++) {
    diff |= pBuf[i] ^ eBuf[i];
  }

  return diff === 0;
}
