// lib/api.ts
export type TextReportBlock = {
  type?: string;
  text?: string;
  [key: string]: unknown;
};

export type AgentReport = {
  report?: string | TextReportBlock[] | Record<string, unknown>;
  [key: string]: unknown;
};

export type PlanResponse = {
  messages?: string[];
  final_report?: {
    planning?: AgentReport;
    manufacturing?: AgentReport;
    schemes?: AgentReport;
    research?: AgentReport;
  };
  [key: string]: unknown;
};

export type AuthUser = {
  id: number;
  email: string;
  role: string;
};

export type AuthResponse = {
  token: string;
  userId: number;
  email: string;
  role: string;
};

export type AdminDashboardResponse = {
  message: string;
  status: string;
  role: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail ?? "Request failed");
  }

  return res.json();
}

export async function loginUser(email: string, password: string) {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function registerUser(email: string, password: string) {
  return request<AuthResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchProfile(token: string) {
  return request<AuthUser>("/api/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export async function fetchAdminDashboard(token: string) {
  return request<AdminDashboardResponse>("/api/admin/dashboard", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export async function generatePlan(
  query: string,
  token: string,
): Promise<PlanResponse> {
  return request<PlanResponse>("/api/plan", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query }),
  });
}

export type BackendPlanItem = {
  id: string;
  query: string;
  title?: string;
  created_at: string;
  plan_data: PlanResponse;
};

export async function fetchUserPlans(token: string): Promise<BackendPlanItem[]> {
  return request<BackendPlanItem[]>("/api/plans", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export async function deleteUserPlan(planId: string, token: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/plans/${planId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export async function clearAllUserPlans(token: string): Promise<{ status: string }> {
  return request<{ status: string }>("/api/plans", {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export type LivePlace = {
  source: "google_places";
  place_id?: string;
  name?: string;
  formatted_address?: string;
  latitude?: number;
  longitude?: number;
  business_status?: string;
  rating?: number;
  user_rating_count?: number;
  website_uri?: string;
  maps_uri?: string;
};

export type IndustryLocation = {
  id: string;
  name: string;
  state: string;
  district: string;
  sector: string;
  industrial_park_type: string;
  park_type: string;
  land_category: string;
  land_available_hectares: number;
  total_land_hectares: number;
  plug_and_play: boolean;
  updated_at: string;
  score: number;
  match_reasons: string[];
  maps_url: string;
  live_place: LivePlace | null;
  summary: string;
};

export type LocationAdvantagePillars = {
  supply_chain_ecosystem: string;
  state_subsidies_policy: string;
  logistics_connectivity: string;
  spcb_clearance_siting: string;
  skilled_workforce: string;
};

export type LocationRecommendation = {
  sector: string;
  recommended_state: string;
  recommended_district: string;
  recommended_cluster: string;
  suitability_score: number;
  why_recommended_summary: string;
  key_advantages: LocationAdvantagePillars;
};

export type LocationSearchResponse = {
  query: string;
  mode?: "auto" | "specific" | "recommendation";
  user_specified_location?: string | null;
  recommendation?: LocationRecommendation | null;
  total_catalogue_locations: number;
  google_places_enrichment: "enabled" | "not_configured";
  results: IndustryLocation[];
  disclaimer: string;
};

export async function fetchLocationStates(token: string) {
  return request<string[]>("/api/locations/states", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function searchIndustryLocations(
  query: string,
  token: string,
  options: {
    limit?: number;
    enrich?: boolean;
    state_filter?: string | null;
    mode?: "auto" | "specific" | "recommendation";
  } = {},
) {
  return request<LocationSearchResponse>("/api/locations/search", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      query,
      limit: options.limit ?? 5,
      enrich: options.enrich ?? true,
      state_filter: options.state_filter ?? null,
      mode: options.mode ?? "auto",
    }),
  });
}

export async function recommendOptimalLocation(
  industry_description: string,
  token: string,
  options: {
    state_preference?: string | null;
    limit?: number;
    enrich?: boolean;
  } = {},
) {
  return request<LocationSearchResponse>("/api/locations/recommend", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      industry_description,
      state_preference: options.state_preference ?? null,
      limit: options.limit ?? 5,
      enrich: options.enrich ?? true,
    }),
  });
}
