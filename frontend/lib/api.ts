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

