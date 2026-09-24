"""API behaviour over the demo seed: auth, role checks, visibility scoping (404), the shared
error body, filters and pagination, dashboards, CORS."""

import pytest

from app.models import Invoice, PurchaseOrder, PurchaseRequest

# ---- auth ---------------------------------------------------------------------------------------


def test_login_and_me(api):
    r = api.client.post("/api/auth/login", json={"email": "Head.Ops@example.com", "password": "demo123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = api.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert (me["email"], me["role"], me["department"]["name"]) == ("head.ops@example.com", "DEPT_HEAD", "Operations")


def test_swagger_form_login(api):
    r = api.client.post("/api/auth/token", data={"username": "finance@example.com", "password": "demo123"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


@pytest.mark.parametrize("headers, code", [
    ({}, "UNAUTHORIZED"),
    ({"Authorization": "Bearer not.a.jwt"}, "UNAUTHORIZED"),
])
def test_requests_without_a_valid_token_get_401(api, headers, code):
    r = api.client.get("/api/prs", headers=headers)
    assert r.status_code == 401 and r.json()["error"] == code


def test_wrong_password(api):
    r = api.client.post("/api/auth/login", json={"email": "finance@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json() == {"error": "INVALID_CREDENTIALS", "message": "Incorrect email or password"}


# ---- role checks (403) ---------------------------------------------------------------------------


@pytest.mark.parametrize("user, method, url", [
    ("store", "get", "/api/prs"),
    ("accounts", "get", "/api/prs"),
    ("requester.it", "get", "/api/payments"),
    ("purchase", "get", "/api/payments"),
    ("store", "get", "/api/invoices"),
    ("finance", "get", "/api/grns"),
    ("requester.it", "get", "/api/suppliers"),
    ("purchase", "get", "/api/users"),
    ("store", "get", "/api/settings"),
    ("admin", "post", "/api/prs"),
    ("purchase", "post", "/api/suppliers"),
    ("finance", "put", "/api/settings/FINANCE_APPROVAL_THRESHOLD"),
])
def test_roles_are_checked_on_every_endpoint(api, user, method, url):
    r = getattr(api.as_(user), method)(url, **({"json": {}} if method != "get" else {}))
    assert r.status_code == 403, r.text
    assert r.json()["error"] == "FORBIDDEN"


def test_admin_reads_everything_but_cannot_act(api):
    admin = api.as_("admin")
    pr7 = api.id(PurchaseRequest, "PR-0007")
    detail = admin.get(f"/api/prs/{pr7}").json()
    assert detail["actions"] == [] and detail["budget"]["over_budget"] is True
    r = admin.post(f"/api/prs/{pr7}/approve")
    assert r.status_code == 403
    assert r.json()["message"] == "This action requires one of the roles DEPT_HEAD, FINANCE; you are ADMIN"
    for url in ("/api/pos", "/api/grns", "/api/invoices", "/api/payments", "/api/users", "/api/audit-logs"):
        assert admin.get(url).status_code == 200, url
    po3 = admin.get(f"/api/pos/{api.id(PurchaseOrder, 'PO-0003')}").json()
    assert po3["actions"] == [] and po3["goods_receipts"] and po3["invoices"] and po3["payments"] == []


# ---- visibility (404) ----------------------------------------------------------------------------


def test_out_of_scope_records_are_404(api):
    po3 = api.id(PurchaseOrder, "PO-0003")  # Operations
    r = api.as_("requester.it").get(f"/api/pos/{po3}")
    assert r.status_code == 404
    assert r.json() == {"error": "NOT_FOUND", "message": f"Purchase order {po3} not found"}
    assert api.as_("requester.ops").get(f"/api/pos/{po3}").status_code == 200


def test_acting_on_another_departments_pr_is_404_not_403(api):
    pr7 = api.id(PurchaseRequest, "PR-0007")  # Operations, pending dept head
    assert api.as_("head.it").post(f"/api/prs/{pr7}/approve").status_code == 404


def test_draft_is_visible_only_to_its_author(api):
    draft = api.id(PurchaseRequest, "PR-0008")
    assert api.as_("requester.it").get(f"/api/prs/{draft}").json()["actions"] == ["edit", "delete", "submit"]
    for user in ("head.it", "finance", "admin", "purchase"):
        assert api.as_(user).get(f"/api/prs/{draft}").status_code == 404, user
    timeline = api.as_("head.it").get("/api/audit-logs", params={"entity_type": "PURCHASE_REQUEST",
                                                                  "entity_id": draft}).json()
    assert timeline["total"] == 0


def test_list_endpoints_are_scoped(api):
    numbers = lambda r: sorted(i.get("pr_number") or i.get("po_number") for i in r.json()["items"])  # noqa: E731
    assert numbers(api.as_("requester.ops").get("/api/prs")) == ["PR-0003", "PR-0004", "PR-0007"]
    assert numbers(api.as_("purchase").get("/api/prs")) == ["PR-0001", "PR-0002", "PR-0003", "PR-0005"]
    assert numbers(api.as_("head.it").get("/api/pos")) == ["PO-0001", "PO-0002"]


def test_detail_hides_parts_the_role_cannot_see(api):
    po2 = api.id(PurchaseOrder, "PO-0002")
    finance = api.as_("finance").get(f"/api/pos/{po2}").json()
    assert finance["goods_receipts"] is None and len(finance["invoices"]) == 2 and len(finance["payments"]) == 1
    store = api.as_("store").get(f"/api/pos/{po2}").json()
    assert store["invoices"] is None and store["payments"] is None and len(store["goods_receipts"]) == 1
    assert {t["entity_type"] for t in store["timeline"]} == {"PURCHASE_ORDER"}
    inv = api.id(Invoice, "SSST/26-27/0923")
    assert api.as_("purchase").get(f"/api/invoices/{inv}").json()["payments"] is None


# ---- error body ----------------------------------------------------------------------------------


def test_invalid_transition_is_409(api):
    pr5 = api.id(PurchaseRequest, "PR-0005")  # APPROVED
    r = api.as_("requester.it").post(f"/api/prs/{pr5}/submit")
    assert r.status_code == 409
    assert r.json() == {"error": "INVALID_TRANSITION",
                        "message": "Cannot submit purchase request PR-0005: it is APPROVED (allowed only when DRAFT)"}


def test_rule_violation_and_validation_are_422(api):
    pr7 = api.id(PurchaseRequest, "PR-0007")
    neha = api.as_("head.ops")
    blank = neha.post(f"/api/prs/{pr7}/reject", json={"comment": "  "})
    assert (blank.status_code, blank.json()["error"]) == (422, "BUSINESS_RULE_VIOLATION")
    assert blank.json()["message"] == "A comment explaining the rejection is required"
    missing = neha.post(f"/api/prs/{pr7}/reject", json={})
    assert (missing.status_code, missing.json()["error"]) == (422, "VALIDATION_ERROR")
    assert missing.json()["message"] == "comment: Field required"


def test_multiple_problems_come_back_together(api):
    items = {i["name"]: i["id"] for i in api.as_("requester.it").get("/api/items").json()}
    r = api.as_("requester.it").post("/api/prs", json={
        "justification": "x", "required_by": "2026-10-01",
        "lines": [{"item_id": items["Wireless Mouse"], "quantity": "0", "estimated_unit_price": "10"},
                  {"item_id": items["Wireless Mouse"], "quantity": "1", "estimated_unit_price": "-1"}]})
    assert r.status_code == 422
    assert len(r.json()["details"]) == 3


def test_unknown_routes_and_methods_use_the_same_error_body(api):
    finance = api.as_("finance")
    assert finance.get("/api/nope").json() == {"error": "NOT_FOUND", "message": "Not found"}
    r = finance.delete("/api/pos")
    assert (r.status_code, r.json()["error"]) == (405, "METHOD_NOT_ALLOWED")


# ---- filters and pagination ----------------------------------------------------------------------


def test_pagination(api):
    page = api.as_("finance").get("/api/prs", params={"page_size": 3, "page": 2}).json()
    assert (page["total"], page["pages"], page["page"], len(page["items"])) == (7, 3, 2, 3)
    assert [p["pr_number"] for p in page["items"]] == ["PR-0004", "PR-0003", "PR-0002"]  # newest first
    assert api.as_("finance").get("/api/prs", params={"page_size": 500}).status_code == 422


def test_filters(api):
    finance = api.as_("finance")
    pending = finance.get("/api/prs", params=[("status", "PENDING_DEPT_HEAD"), ("status", "PENDING_FINANCE")]).json()
    assert sorted(p["pr_number"] for p in pending["items"]) == ["PR-0006", "PR-0007"]
    ops = finance.get("/api/departments").json()
    ops_id = next(d["id"] for d in ops if d["name"] == "Operations")
    assert finance.get("/api/prs", params={"department_id": ops_id}).json()["total"] == 3
    assert finance.get("/api/prs", params={"q": "laptop"}).json()["items"][0]["pr_number"] == "PR-0005"
    assert finance.get("/api/pos", params={"department_id": ops_id}).json()["items"][0]["po_number"] == "PO-0003"
    mismatches = finance.get("/api/invoices", params={"status": "MISMATCH"}).json()
    assert [i["supplier_invoice_number"] for i in mismatches["items"]] == ["SSST/26-27/0923"]
    assert finance.get("/api/prs", params={"created_from": "2026-09-16"}).json()["total"] == 0
    assert finance.get("/api/prs", params={"created_to": "2026-09-15"}).json()["total"] == 7
    mine = api.as_("head.it").get("/api/prs", params={"mine": True}).json()
    assert [p["pr_number"] for p in mine["items"]] == ["PR-0006"]


# ---- dashboards ----------------------------------------------------------------------------------


def test_finance_dashboard(api):
    d = api.as_("finance").get("/api/dashboard").json()
    assert [p["pr_number"] for p in d["pending_approvals"]] == ["PR-0006"]
    assert d["pending_payments"]["count"] == 1 and d["pending_payments"]["total_due"] == "38000.00"
    assert [i["supplier_invoice_number"] for i in d["mismatch_invoices"]] == ["SSST/26-27/0923"]
    spend = {s["department"]["name"]: s for s in d["spend_vs_budget"]}
    assert (spend["Operations"]["committed"], spend["IT"]["committed"], spend["HR"]["committed"]) == \
        ("55000.00", "656500.00", "0.00")
    assert d["pos_by_status"] == {"CLOSED": 1, "SHORT_CLOSED": 1, "PARTIALLY_RECEIVED": 1}
    assert d["my_requests"] is None and len(d["recent_activity"]) == 10


def test_dept_head_dashboard_shows_the_over_budget_warning(api):
    d = api.as_("head.ops").get("/api/dashboard").json()
    [pending] = d["pending_approvals"]
    assert (pending["pr_number"], pending["budget"]["over_budget"], pending["budget"]["projected"]) == \
        ("PR-0007", True, "504000.00")
    assert [s["department"]["name"] for s in d["spend_vs_budget"]] == ["Operations"]
    assert d["pending_payments"] is None


def test_store_and_requester_dashboards(api):
    store = api.as_("store").get("/api/dashboard").json()
    assert (store["pending_approvals"], store["mismatch_invoices"], store["spend_vs_budget"]) == (None, None, None)
    assert sum(store["pos_by_status"].values()) == 3
    riya = api.as_("requester.it").get("/api/dashboard").json()
    assert riya["my_requests"]["DRAFT"] == 1 and riya["my_requests"]["PO_CREATED"] == 2
    refs = {a["reference"] for a in riya["recent_activity"]}
    assert not refs & {"PR-0003", "PO-0003", "PR-0007"}  # nothing from Operations


# ---- masters -------------------------------------------------------------------------------------


def test_admin_manages_masters(api):
    admin = api.as_("admin")
    r = admin.post("/api/suppliers", json={"name": "Acme Tools", "contact_person": "A", "email": "a@acme.in",
                                           "phone": "1", "gstin": "27AABCA1234D1Z5"})
    assert r.status_code == 201
    r = admin.put("/api/settings/FINANCE_APPROVAL_THRESHOLD", json={"value": "75000"})
    assert r.json() == {"key": "FINANCE_APPROVAL_THRESHOLD", "value": "75000.00"}
    assert api.as_("finance").get("/api/settings").json() == [{"key": "FINANCE_APPROVAL_THRESHOLD", "value": "75000.00"}]
    users = admin.get("/api/users", params={"role": "REQUESTER"}).json()
    riya = next(u for u in users if u["email"] == "requester.it@example.com")
    r = admin.patch(f"/api/users/{riya['id']}", json={"is_active": False})
    assert r.json()["is_active"] is False
    assert api.as_("requester.it").get("/api/prs").status_code == 401  # deactivation applies at once


# ---- CORS ----------------------------------------------------------------------------------------


def test_cors_allows_the_next_dev_server(api):
    r = api.client.options("/api/prs", headers={"Origin": "http://localhost:3000",
                                                "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = api.client.options("/api/prs", headers={"Origin": "http://evil.example",
                                                    "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in other.headers
