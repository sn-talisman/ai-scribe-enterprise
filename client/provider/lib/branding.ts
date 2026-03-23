/**
 * client/provider/lib/branding.ts — Practice branding configuration loader.
 *
 * Reads branding config (practice_name, logo_url, primary_color) from the
 * deployment API. Falls back to default "AI Scribe" branding when the
 * endpoint is unavailable or returns an error.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface BrandingConfig {
  practice_name: string;
  logo_url: string;
  primary_color: string;
}

export const DEFAULT_BRANDING: BrandingConfig = {
  practice_name: "AI Scribe",
  logo_url: "",
  primary_color: "#1a5276",
};

/**
 * Fetch branding configuration from the API.
 * Returns DEFAULT_BRANDING on any failure (404, network error, etc.).
 */
export async function fetchBranding(): Promise<BrandingConfig> {
  try {
    const res = await fetch(`${BASE}/config/branding`, { cache: "no-store" });
    if (!res.ok) return DEFAULT_BRANDING;
    const data = await res.json();
    return {
      practice_name: data.practice_name ?? DEFAULT_BRANDING.practice_name,
      logo_url: data.logo_url ?? DEFAULT_BRANDING.logo_url,
      primary_color: data.primary_color ?? DEFAULT_BRANDING.primary_color,
    };
  } catch {
    return DEFAULT_BRANDING;
  }
}
