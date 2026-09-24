// Typed client for every backend endpoint (see backend/app/api/routers). The JWT lives in
// memory, mirrored to sessionStorage so a page reload keeps the tab logged in; each tab can
// be a different demo user.

import type {
  AdminUser,
  Comparison,
  CurrentUser,
  Dashboard,
  DemoUsers,
  Department,
  EntityType,
  GRN,
  GRNIn,
  InvoiceDetail,
  InvoiceIn,
  InvoiceListItem,
  InvoiceStatus,
  Item,
  Page,
  Payment,
  PaymentIn,
  PaymentMode,
  PendingApproval,
  PODetail,
  POListItem,
  POStatus,
  PRDetail,
  PRIn,
  PRListItem,
  PRStatus,
  Quotation,
  QuotationIn,
  Receivable,
  Role,
  SelectIn,
  Setting,
  Supplier,
  TimelineEntry,
  TokenResponse,
  Budget,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const TOKEN_KEY = "pms.token";

/** An error response from the API: `message` is written for humans and shown as-is. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

// ---- token ----------------------------------------------------------------------------------------

let memoryToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export const tokenStore = {
  get(): string | null {
    if (memoryToken === null && typeof window !== "undefined") {
      memoryToken = window.sessionStorage.getItem(TOKEN_KEY);
    }
    return memoryToken;
  },
  set(token: string) {
    memoryToken = token;
    window.sessionStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    memoryToken = null;
    if (typeof window !== "undefined") window.sessionStorage.removeItem(TOKEN_KEY);
  },
};

/** Called once by the auth provider: what to do when the API says the session is gone. */
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

// ---- transport ------------------------------------------------------------------------------------

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

function toQueryString(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.append(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function request<T>(method: string, path: string, options: { body?: unknown; query?: Query } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}${toQueryString(options.query)}`, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", `Cannot reach the server at ${API_URL}. Is the backend running?`);
  }

  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.message ?? `Request failed (${response.status})`;
    const error = new ApiError(response.status, payload?.error ?? `HTTP_${response.status}`, message, payload?.details);
    if (response.status === 401 && token && unauthorizedHandler) unauthorizedHandler();
    throw error;
  }
  return payload as T;
}

const get = <T>(path: string, query?: Query) => request<T>("GET", path, { query });
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} });
const put = <T>(path: string, body: unknown) => request<T>("PUT", path, { body });
const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, { body });
const del = (path: string) => request<void>("DELETE", path);

// ---- filters --------------------------------------------------------------------------------------

export interface Paging { page?: number; page_size?: number }
export interface PRFilters extends Paging {
  status?: PRStatus[]; department_id?: number; requester_id?: number; mine?: boolean;
  created_from?: string; created_to?: string; q?: string;
}
export interface POFilters extends Paging {
  status?: POStatus[]; supplier_id?: number; department_id?: number; pr_id?: number;
  created_from?: string; created_to?: string; q?: string;
}
export interface InvoiceFilters extends Paging {
  status?: InvoiceStatus[]; supplier_id?: number; po_id?: number; invoice_from?: string; invoice_to?: string; q?: string;
}
export interface GRNFilters extends Paging { po_id?: number; received_from?: string; received_to?: string }
export interface PaymentFilters extends Paging {
  supplier_id?: number; mode?: PaymentMode; invoice_id?: number; paid_from?: string; paid_to?: string;
}
export interface AuditFilters extends Paging {
  entity_type?: EntityType; entity_id?: number; action?: string; at_from?: string; at_to?: string; order?: "asc" | "desc";
}

// ---- endpoints ------------------------------------------------------------------------------------

export const api = {
  auth: {
    login: (email: string, password: string) => post<TokenResponse>("/auth/login", { email, password }),
    me: () => get<CurrentUser>("/auth/me"),
    demoUsers: () => get<DemoUsers>("/auth/demo-users"),
  },
  dashboard: () => get<Dashboard>("/dashboard"),
  auditLogs: (filters: AuditFilters = {}) => get<Page<TimelineEntry>>("/audit-logs", { ...filters }),

  prs: {
    list: (filters: PRFilters = {}) => get<Page<PRListItem>>("/prs", { ...filters }),
    get: (id: number) => get<PRDetail>(`/prs/${id}`),
    create: (body: PRIn) => post<PRDetail>("/prs", body),
    update: (id: number, body: PRIn) => put<PRDetail>(`/prs/${id}`, body),
    remove: (id: number) => del(`/prs/${id}`),
    submit: (id: number) => post<PRDetail>(`/prs/${id}/submit`),
    approve: (id: number, comment?: string) => post<PRDetail>(`/prs/${id}/approve`, { comment: comment || null }),
    reject: (id: number, comment: string) => post<PRDetail>(`/prs/${id}/reject`, { comment }),
    budgetCheck: (id: number) => get<Budget>(`/prs/${id}/budget-check`),
    pendingApprovals: () => get<PendingApproval[]>("/approvals/pending"),
  },

  quotations: {
    list: (prId: number) => get<Quotation[]>(`/prs/${prId}/quotations`),
    add: (prId: number, body: QuotationIn) => post<Quotation>(`/prs/${prId}/quotations`, body),
    compare: (prId: number) => get<Comparison>(`/prs/${prId}/quotations/comparison`),
    select: (prId: number, quotationId: number, body: SelectIn) =>
      post<PODetail>(`/prs/${prId}/quotations/${quotationId}/select`, body),
    update: (id: number, body: Omit<QuotationIn, "supplier_id">) => put<Quotation>(`/quotations/${id}`, body),
    remove: (id: number) => del(`/quotations/${id}`),
  },

  pos: {
    list: (filters: POFilters = {}) => get<Page<POListItem>>("/pos", { ...filters }),
    get: (id: number) => get<PODetail>(`/pos/${id}`),
    cancel: (id: number, reason: string) => post<PODetail>(`/pos/${id}/cancel`, { reason }),
    shortClose: (id: number, reason: string) => post<PODetail>(`/pos/${id}/short-close`, { reason }),
    receivable: (id: number) => get<Receivable>(`/pos/${id}/receivable`),
    recordGrn: (id: number, body: GRNIn) => post<GRN>(`/pos/${id}/grns`, body),
    enterInvoice: (id: number, body: InvoiceIn) => post<InvoiceDetail>(`/pos/${id}/invoices`, body),
  },

  grns: {
    list: (filters: GRNFilters = {}) => get<Page<GRN>>("/grns", { ...filters }),
    get: (id: number) => get<GRN>(`/grns/${id}`),
  },

  invoices: {
    list: (filters: InvoiceFilters = {}) => get<Page<InvoiceListItem>>("/invoices", { ...filters }),
    get: (id: number) => get<InvoiceDetail>(`/invoices/${id}`),
    rematch: (id: number) => post<InvoiceDetail>(`/invoices/${id}/rematch`),
    reject: (id: number, reason: string) => post<InvoiceDetail>(`/invoices/${id}/reject`, { reason }),
    pay: (id: number, body: PaymentIn) => post<InvoiceDetail>(`/invoices/${id}/payments`, body),
    payments: (id: number) => get<Payment[]>(`/invoices/${id}/payments`),
  },

  payments: {
    list: (filters: PaymentFilters = {}) => get<Page<Payment>>("/payments", { ...filters }),
  },

  masters: {
    departments: () => get<Department[]>("/departments"),
    createDepartment: (body: { name: string; monthly_budget: string }) => post<Department>("/departments", body),
    updateDepartment: (id: number, body: Partial<{ name: string; monthly_budget: string }>) =>
      patch<Department>(`/departments/${id}`, body),
    users: (query: { role?: Role; department_id?: number; active?: boolean; q?: string } = {}) =>
      get<AdminUser[]>("/users", query),
    createUser: (body: { name: string; email: string; password: string; role: Role; department_id: number | null }) =>
      post<AdminUser>("/users", body),
    updateUser: (id: number, body: Partial<{ name: string; email: string; role: Role; department_id: number | null;
      is_active: boolean; password: string }>) => patch<AdminUser>(`/users/${id}`, body),
    suppliers: (query: { active?: boolean; q?: string } = {}) => get<Supplier[]>("/suppliers", query),
    createSupplier: (body: Omit<Supplier, "id" | "is_active">) => post<Supplier>("/suppliers", body),
    updateSupplier: (id: number, body: Partial<Omit<Supplier, "id">>) => patch<Supplier>(`/suppliers/${id}`, body),
    items: (query: { category?: string; q?: string } = {}) => get<Item[]>("/items", query),
    createItem: (body: Omit<Item, "id">) => post<Item>("/items", body),
    updateItem: (id: number, body: Partial<Omit<Item, "id">>) => patch<Item>(`/items/${id}`, body),
    settings: () => get<Setting[]>("/settings"),
    putSetting: (key: string, value: string) => put<Setting>(`/settings/${key}`, { value }),
  },
};
