// Types mirroring the backend's Pydantic schemas (backend/app/schemas). Money and quantities
// arrive as decimal strings ("73500.00", "50.000") and are only formatted, never computed on.

export type Decimal = string;
export type ISODate = string; // YYYY-MM-DD
export type ISODateTime = string;

export type Role = "REQUESTER" | "DEPT_HEAD" | "FINANCE" | "PURCHASE" | "STORE" | "ACCOUNTS" | "ADMIN";
export type PRStatus = "DRAFT" | "PENDING_DEPT_HEAD" | "PENDING_FINANCE" | "APPROVED" | "REJECTED" | "PO_CREATED";
export type POStatus = "ISSUED" | "PARTIALLY_RECEIVED" | "FULLY_RECEIVED" | "SHORT_CLOSED" | "CLOSED" | "CANCELLED";
export type InvoiceStatus = "PENDING_MATCH" | "MATCHED" | "MISMATCH" | "PARTIALLY_PAID" | "PAID" | "REJECTED";
export type AnyStatus = PRStatus | POStatus | InvoiceStatus;
export type PaymentMode = "NEFT" | "CHEQUE" | "UPI";
export type ItemUnit = "pcs" | "kg" | "box";
export type ApprovalLevel = "DEPT_HEAD" | "FINANCE";
export type EntityType = "PURCHASE_REQUEST" | "PURCHASE_ORDER" | "INVOICE";

export type PRAction =
  | "edit" | "delete" | "submit" | "resubmit" | "approve" | "reject" | "add_quotation" | "select_quotation";
export type POAction = "cancel" | "short_close" | "record_grn" | "enter_invoice";
export type InvoiceAction = "rematch" | "reject" | "record_payment";

// ---- shared -----------------------------------------------------------------------------------

export interface UserRef { id: number; name: string; role: Role }
export interface DepartmentRef { id: number; name: string }
export interface SupplierRef { id: number; name: string }
export interface ItemRef { id: number; name: string; unit: ItemUnit; category: string }

export interface TimelineEntry {
  at: ISODateTime;
  entity_type: EntityType;
  entity_id: number;
  reference: string | null;
  action: string;
  from_status: string | null;
  to_status: string | null;
  user: UserRef | null;
  details: Record<string, unknown> | null;
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number; pages: number }

export interface ApiErrorBody { error: string; message: string; details?: unknown }

// ---- auth -------------------------------------------------------------------------------------

export interface CurrentUser { id: number; name: string; email: string; role: Role; department: DepartmentRef | null }
export interface TokenResponse { access_token: string; token_type: string; expires_in: number; user: CurrentUser }
export interface DemoUsers { password: string; users: CurrentUser[] }

// ---- masters ----------------------------------------------------------------------------------

export interface Department { id: number; name: string; monthly_budget: Decimal }
export interface AdminUser {
  id: number; name: string; email: string; role: Role; department: DepartmentRef | null;
  is_active: boolean; created_at: ISODateTime;
}
export interface Supplier {
  id: number; name: string; contact_person: string; email: string; phone: string; gstin: string; is_active: boolean;
}
export interface Item { id: number; name: string; unit: ItemUnit; category: string }
export interface Setting { key: string; value: string }

// ---- purchase requests --------------------------------------------------------------------------

export interface PRLineIn { item_id: number; quantity: string; estimated_unit_price: string }
export interface PRIn { justification: string; required_by: ISODate; lines: PRLineIn[] }

export interface PRLine { id: number; item: ItemRef; quantity: Decimal; estimated_unit_price: Decimal; line_total: Decimal }
export interface Approval {
  level: ApprovalLevel; action: "APPROVED" | "REJECTED"; approver: UserRef; comment: string | null;
  over_budget: boolean; at: ISODateTime;
}
export interface Budget {
  department: string; monthly_budget: Decimal; approved_this_month: Decimal; this_request: Decimal;
  projected: Decimal; remaining_after: Decimal; over_budget: boolean;
}
export interface POLink { id: number; po_number: string; status: POStatus; total: Decimal; supplier: SupplierRef }

export interface PRListItem {
  id: number; pr_number: string; status: PRStatus; requester: UserRef; department: DepartmentRef;
  justification: string; estimated_total: Decimal; required_by: ISODate; created_at: ISODateTime;
  submitted_at: ISODateTime | null; final_approved_at: ISODateTime | null;
}
export interface PRDetail extends PRListItem {
  rejection_reason: string | null; updated_at: ISODateTime; lines: PRLine[]; approvals: Approval[];
  budget: Budget | null; quotation_count: number | null; purchase_orders: POLink[] | null;
  timeline: TimelineEntry[]; actions: PRAction[];
}
export interface PendingApproval extends PRListItem { level: ApprovalLevel; budget: Budget }

// ---- quotations -------------------------------------------------------------------------------

export interface QuoteLineIn { pr_line_id: number; unit_price: string }
export interface QuotationIn {
  supplier_id: number; quote_date: ISODate; valid_until: ISODate; delivery_days: number;
  payment_terms: string; lines: QuoteLineIn[];
}
export interface QuoteLine { id: number; pr_line_id: number; item: ItemRef; quantity: Decimal; unit_price: Decimal; line_total: Decimal }
export interface Quotation {
  id: number; pr_id: number; supplier: SupplierRef; quote_date: ISODate; valid_until: ISODate;
  delivery_days: number; payment_terms: string; total: Decimal; is_selected: boolean; is_expired: boolean;
  created_at: ISODateTime; lines: QuoteLine[];
}
export interface SelectIn { selection_reason?: string | null; single_quote_justification?: string | null }

export interface ComparisonQuotation {
  quotation_id: number; supplier: SupplierRef; total: Decimal; delivery_days: number; payment_terms: string;
  quote_date: ISODate; valid_until: ISODate; is_expired: boolean; is_selected: boolean; is_lowest_valid_total: boolean;
}
export interface ComparisonCell { quotation_id: number; unit_price: Decimal; line_total: Decimal; is_lowest: boolean }
export interface ComparisonRow { pr_line_id: number; item: ItemRef; quantity: Decimal; cells: ComparisonCell[] }
export interface SelectionHints {
  valid_quotations: number; single_quote_justification_required: boolean;
  lowest_valid_total: Decimal | null; lowest_valid_quotation_ids: number[];
}
export interface Comparison {
  pr_id: number; pr_number: string; pr_status: PRStatus; quotations: ComparisonQuotation[];
  lines: ComparisonRow[]; selection: SelectionHints;
}

// ---- purchase orders, GRNs, payments ----------------------------------------------------------

export interface PRRef { id: number; pr_number: string; status: PRStatus; department: DepartmentRef; requester: UserRef }
export interface PORef { id: number; po_number: string; status: POStatus; supplier: SupplierRef }
export interface POLine {
  id: number; item: ItemRef; qty_ordered: Decimal; unit_price: Decimal; line_total: Decimal;
  qty_accepted: Decimal; qty_invoiced: Decimal; qty_pending_receipt: Decimal; qty_uninvoiced: Decimal;
}
export interface POListItem {
  id: number; po_number: string; status: POStatus; supplier: SupplierRef; pr: PRRef; total: Decimal;
  created_at: ISODateTime; updated_at: ISODateTime;
}
export interface GRNLine {
  id: number; po_line_id: number; item: ItemRef; qty_received: Decimal; qty_accepted: Decimal;
  qty_rejected: Decimal; rejection_reason: string | null;
}
export interface GRN {
  id: number; grn_number: string; po: PORef; received_date: ISODate; received_by: UserRef;
  remarks: string | null; created_at: ISODateTime; lines: GRNLine[];
}
export interface GRNLineIn {
  po_line_id: number; qty_received: string; qty_accepted: string; qty_rejected: string; rejection_reason: string | null;
}
export interface GRNIn { received_date: ISODate; remarks: string | null; lines: GRNLineIn[] }
export interface ReceivableLine { po_line_id: number; item: ItemRef; qty_ordered: Decimal; qty_accepted: Decimal; qty_pending: Decimal }
export interface Receivable { po: PORef; lines: ReceivableLine[] }

export interface InvoiceLink {
  id: number; supplier_invoice_number: string; status: InvoiceStatus; invoice_date: ISODate;
  total: Decimal; amount_paid: Decimal; balance_due: Decimal;
}
export interface Payment {
  id: number; invoice_id: number; supplier_invoice_number: string; po_number: string; supplier: SupplierRef;
  amount: Decimal; mode: PaymentMode; reference_no: string; paid_on: ISODate; recorded_by: UserRef; created_at: ISODateTime;
}
export interface PODetail extends POListItem {
  quotation_id: number; selection_reason: string | null; single_quote_justification: string | null;
  cancel_reason: string | null; short_close_reason: string | null; created_by: UserRef; lines: POLine[];
  goods_receipts: GRN[] | null; invoices: InvoiceLink[] | null; payments: Payment[] | null;
  timeline: TimelineEntry[]; actions: POAction[];
}

// ---- invoices -----------------------------------------------------------------------------------

export interface InvoiceLineIn { po_line_id: number; qty: string; unit_price: string }
export interface InvoiceIn { supplier_invoice_number: string; invoice_date: ISODate; total: string; lines: InvoiceLineIn[] }
export interface InvoiceLine {
  id: number; po_line_id: number; item: ItemRef; qty: Decimal; unit_price: Decimal; line_total: Decimal;
  po_unit_price: Decimal; price_matches: boolean;
}
export interface InvoiceListItem {
  id: number; supplier_invoice_number: string; status: InvoiceStatus; po: PORef; supplier: SupplierRef;
  invoice_date: ISODate; total: Decimal; amount_paid: Decimal; balance_due: Decimal; created_at: ISODateTime;
}
export interface InvoiceDetail extends InvoiceListItem {
  lines: InvoiceLine[]; mismatch_reasons: string[]; rejection_reason: string | null; created_by: UserRef;
  payments: Payment[] | null; timeline: TimelineEntry[]; actions: InvoiceAction[];
}
export interface PaymentIn { amount: string; mode: PaymentMode; reference_no: string; paid_on: ISODate }

// ---- dashboard ----------------------------------------------------------------------------------

export interface DepartmentSpend {
  department: DepartmentRef; monthly_budget: Decimal; committed: Decimal; remaining: Decimal;
  utilisation_pct: Decimal; over_budget: boolean;
}
export interface Dashboard {
  pending_approvals: PendingApproval[] | null;
  my_requests: Record<PRStatus, number> | null;
  pos_by_status: Partial<Record<POStatus, number>> | null;
  mismatch_invoices: InvoiceListItem[] | null;
  pending_payments: { count: number; total_due: Decimal; invoices: InvoiceListItem[] } | null;
  spend_vs_budget: DepartmentSpend[] | null;
  recent_activity: TimelineEntry[];
}
