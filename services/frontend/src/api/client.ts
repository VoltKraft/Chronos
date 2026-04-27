const base = "";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status} ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

// H-10: CSRF token cache. Populated lazily on the first unsafe request or
// immediately after login; cleared on logout and whenever the server rejects
// a request because the cached token doesn't match its session copy.
let csrfToken: string | null = null;

const CSRF_HEADER = "X-CSRF-Token";
const CSRF_SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const CSRF_RETRYABLE_DETAILS = new Set([
  "CSRF token mismatch",
  "CSRF token missing in session",
]);

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetch(`${base}/auth/csrf-token`, { credentials: "include" });
  if (!res.ok) {
    // Let the caller surface the underlying reason (likely a 401 from
    // current_user) by throwing an ApiError with the server's detail.
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON body
    }
    throw new ApiError(res.status, detail);
  }
  const body = (await res.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

async function request<T>(path: string, init: RequestInit = {}, _retry = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body && !(init.body instanceof FormData)) {
    headers["content-type"] = "application/json";
  }
  const method = (init.method ?? "GET").toUpperCase();
  if (!CSRF_SAFE_METHODS.has(method)) {
    // Attach the CSRF token on every state-changing request. We skip
    // /auth/login because it creates the session that holds the token in
    // the first place; the server exempts it from the check.
    if (path !== "/auth/login") {
      const token = await getCsrfToken();
      headers[CSRF_HEADER] = token;
    }
  }
  const res = await fetch(`${base}${path}`, {
    credentials: "include",
    ...init,
    headers: { ...headers, ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON body
    }
    // If the server rejected us because the cached CSRF token is stale
    // (e.g. the session was rotated server-side after a re-auth), drop the
    // cache and retry once transparently.
    if (res.status === 403 && !_retry && CSRF_RETRYABLE_DETAILS.has(detail)) {
      csrfToken = null;
      return request<T>(path, init, true);
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export type Role = "employee" | "team_lead" | "hr" | "admin";

export type User = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: Role;
  locale: string;
  time_zone: string;
  department_id: string | null;
  team_id: string | null;
  must_rotate_password: boolean;
};

export type UserDetail = User & { created_at: string; updated_at: string };

export type LeaveType = "VACATION" | "SICK" | "OTHER";
export type LeaveStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "DELEGATE_REVIEW"
  | "TL_REVIEW"
  | "HR_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED"
  | "OVERRIDDEN";

export type LeaveRequest = {
  id: string;
  requester_id: string;
  approver_delegate_id: string | null;
  approver_tl_id: string | null;
  approver_hr_id: string | null;
  type: LeaveType;
  reason: string | null;
  start_date: string;
  end_date: string;
  status: LeaveStatus;
  has_certificate: boolean;
  submitted_at: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Department = { id: string; name: string; created_at: string; updated_at: string };
export type Team = {
  id: string;
  name: string;
  department_id: string;
  created_at: string;
  updated_at: string;
};
export type Project = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type Shift = {
  id: string;
  team_id: string;
  service_date: string;
  shift_type: "EARLY" | "LATE" | "OTHER";
  start_time: string;
  end_time: string;
  required_headcount: number;
  project_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ShiftAssignment = {
  id: string;
  shift_id: string;
  user_id: string;
  status: string;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type Preference = {
  id: string;
  user_id: string;
  preference_type: "SHIFT_TIME" | "DAY_OFF" | "PROJECT";
  payload: Record<string, unknown>;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  updated_at: string;
};

export type Delegate = {
  id: string;
  principal_id: string;
  delegate_user_id: string;
  valid_from: string;
  valid_to: string;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: string;
  seq: number;
  occurred_at: string;
  actor_id: string | null;
  actor_role: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  reason: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  prev_hash: string | null;
  row_hash: string;
};

export type LeaveSummary = {
  user_id: string;
  user_name: string;
  vacation_days: number;
  sickness_days: number;
  other_days: number;
};

export type ShiftSummary = {
  user_id: string;
  user_name: string;
  early_count: number;
  late_count: number;
  other_count: number;
};

export type Workflow = {
  id: string;
  name: string;
  description: string | null;
  definition: { nodes: unknown[]; edges: unknown[] };
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!entries.length) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

export const api = {
  // Auth
  login: async (username: string, password: string) => {
    // The server rotates the session on successful auth and stamps a fresh
    // CSRF secret into it. Drop any stale cached token before the call, and
    // hydrate a fresh one right after so subsequent unsafe requests don't
    // eat a 403/retry round-trip.
    csrfToken = null;
    const user = await request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    try {
      await getCsrfToken();
    } catch {
      // Non-fatal: the token will be fetched lazily on the first unsafe call.
    }
    return user;
  },
  logout: async () => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      // Session is gone on the server either way; wipe the cache so the next
      // login starts clean.
      csrfToken = null;
    }
  },
  me: () => request<User>("/auth/me"),
  getCsrfToken: () => getCsrfToken(),

  // Users
  listUsers: (params: { team_id?: string } = {}) =>
    request<UserDetail[]>("/api/users" + qs(params)),
  createUser: (body: {
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
    role: Role;
    department_id?: string | null;
    team_id?: string | null;
    locale?: string;
    time_zone?: string;
  }) => request<UserDetail>("/api/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: string, body: Partial<UserDetail>) =>
    request<UserDetail>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  setRole: (id: string, role: Role, reason?: string) =>
    request<UserDetail>(`/api/users/${id}/role`, {
      method: "PUT",
      body: JSON.stringify({ role, reason }),
    }),
  setPassword: (id: string, new_password: string) =>
    request<void>(`/api/users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify({ new_password }),
    }),
  changeMyPassword: (current_password: string, new_password: string) =>
    request<void>("/api/users/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  deactivateUser: (id: string) => request<void>(`/api/users/${id}`, { method: "DELETE" }),
  exportMyData: (id: string) => request<string>(`/api/users/${id}/export`),

  // Org
  listDepartments: () => request<Department[]>("/api/departments"),
  createDepartment: (name: string) =>
    request<Department>("/api/departments", { method: "POST", body: JSON.stringify({ name }) }),
  listTeams: (params: { department_id?: string } = {}) =>
    request<Team[]>("/api/teams" + qs(params)),
  createTeam: (name: string, department_id: string) =>
    request<Team>("/api/teams", { method: "POST", body: JSON.stringify({ name, department_id }) }),

  // Projects
  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (body: { code: string; name: string; description?: string | null }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),

  // Leave
  listLeave: (params: { status_filter?: LeaveStatus; requester_id?: string } = {}) =>
    request<LeaveRequest[]>("/api/leave-requests" + qs(params)),
  leaveInbox: () => request<LeaveRequest[]>("/api/leave-requests/inbox"),
  delegateSuggestions: (start_date: string, end_date: string) =>
    request<User[]>("/api/leave-requests/delegate-suggestions" + qs({ start_date, end_date })),
  getLeave: (id: string) => request<LeaveRequest>(`/api/leave-requests/${id}`),
  createLeave: (body: {
    type: LeaveType;
    start_date: string;
    end_date: string;
    reason?: string | null;
    approver_delegate_id?: string | null;
    approver_tl_id?: string | null;
    approver_hr_id?: string | null;
    has_certificate?: boolean;
  }) => request<LeaveRequest>("/api/leave-requests", { method: "POST", body: JSON.stringify(body) }),
  updateLeave: (id: string, body: Partial<LeaveRequest>) =>
    request<LeaveRequest>(`/api/leave-requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  submitLeave: (id: string) =>
    request<LeaveRequest>(`/api/leave-requests/${id}/submit`, { method: "POST" }),
  approveLeave: (id: string, reason?: string) =>
    request<LeaveRequest>(`/api/leave-requests/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  rejectLeave: (id: string, reason?: string) =>
    request<LeaveRequest>(`/api/leave-requests/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  cancelLeave: (id: string) =>
    request<LeaveRequest>(`/api/leave-requests/${id}/cancel`, { method: "POST" }),
  overrideLeave: (id: string, reason: string) =>
    request<LeaveRequest>(`/api/leave-requests/${id}/override`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // Delegates
  listDelegates: (params: { principal_id?: string } = {}) =>
    request<Delegate[]>("/api/delegates" + qs(params)),
  createDelegate: (body: {
    principal_id: string;
    delegate_user_id: string;
    valid_from: string;
    valid_to: string;
  }) => request<Delegate>("/api/delegates", { method: "POST", body: JSON.stringify(body) }),
  deleteDelegate: (id: string) => request<void>(`/api/delegates/${id}`, { method: "DELETE" }),

  // Shifts
  listShifts: (params: { start: string; end: string; team_id?: string }) =>
    request<Shift[]>("/api/shifts" + qs(params)),
  createShift: (body: {
    team_id: string;
    service_date: string;
    shift_type: "EARLY" | "LATE" | "OTHER";
    start_time: string;
    end_time: string;
    required_headcount: number;
    project_id?: string | null;
  }) => request<Shift>("/api/shifts", { method: "POST", body: JSON.stringify(body) }),
  updateShift: (id: string, body: Partial<Shift>) =>
    request<Shift>(`/api/shifts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteShift: (id: string) => request<void>(`/api/shifts/${id}`, { method: "DELETE" }),
  listAssignments: (shift_id: string) =>
    request<ShiftAssignment[]>(`/api/shifts/${shift_id}/assignments`),
  assign: (shift_id: string, body: { user_id: string; status?: string; note?: string | null }) =>
    request<ShiftAssignment>(`/api/shifts/${shift_id}/assignments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  unassign: (shift_id: string, user_id: string) =>
    request<void>(`/api/shifts/${shift_id}/assignments/${user_id}`, { method: "DELETE" }),
  suggestSubstitutes: (shift_id: string) => request<User[]>(`/api/shifts/${shift_id}/substitutes`),
  planShifts: (body: {
    team_id: string;
    period_start: string;
    period_end: string;
    required_per_shift?: number;
    holidays?: string[];
  }) => request<{ shifts_created: number; assignments_created: number; unassigned: string[] }>(
    "/api/shifts/plan",
    { method: "POST", body: JSON.stringify(body) },
  ),

  // Preferences
  listPreferences: (params: { user_id?: string } = {}) =>
    request<Preference[]>("/api/preferences" + qs(params)),
  createPreference: (body: {
    user_id: string;
    preference_type: "SHIFT_TIME" | "DAY_OFF" | "PROJECT";
    payload: Record<string, unknown>;
    effective_from: string;
    effective_to?: string | null;
  }) => request<Preference>("/api/preferences", { method: "POST", body: JSON.stringify(body) }),
  deletePreference: (id: string) => request<void>(`/api/preferences/${id}`, { method: "DELETE" }),

  // Reports & audit
  leaveSummary: (start: string, end: string) =>
    request<LeaveSummary[]>("/api/reports/leave" + qs({ start, end })),
  sicknessSummary: (start: string, end: string) =>
    request<LeaveSummary[]>("/api/reports/sickness" + qs({ start, end })),
  shiftsSummary: (start: string, end: string, team_id?: string) =>
    request<ShiftSummary[]>("/api/reports/shifts" + qs({ start, end, team_id })),
  leaveSummaryCsvUrl: (start: string, end: string) =>
    `/api/reports/leave.csv${qs({ start, end })}`,
  icsUrl: (user_id: string, start?: string, end?: string) =>
    `/api/calendar/${user_id}.ics${qs({ start, end })}`,
  listAudit: (params: { action?: string; actor_id?: string; since?: string; limit?: number } = {}) =>
    request<AuditEvent[]>("/api/audit/events" + qs(params)),
  verifyAudit: () =>
    request<{ ok: boolean; checked: number; first_bad_id: string | null }>("/api/audit/verify"),

  // Workflows (existing)
  listWorkflows: () => request<Workflow[]>("/api/workflows"),
  getWorkflow: (id: string) => request<Workflow>(`/api/workflows/${id}`),
  createWorkflow: (body: { name: string; description?: string | null; definition: Workflow["definition"] }) =>
    request<Workflow>("/api/workflows", { method: "POST", body: JSON.stringify(body) }),
  updateWorkflow: (id: string, body: Partial<{ name: string; description: string | null; definition: Workflow["definition"] }>) =>
    request<Workflow>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteWorkflow: (id: string) => request<void>(`/api/workflows/${id}`, { method: "DELETE" }),
};
