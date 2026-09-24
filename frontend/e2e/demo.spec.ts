import { expect, test } from "@playwright/test";

import { E2E_API } from "../playwright.config";
import { blockExternalRequests, collectPageErrors, loginAs, snap, switchUser, toast } from "./helpers";

// The live demo, end to end in a real browser, each step by the role that owns it. The data is
// the demo seed (fresh for every run); new documents continue its numbering (PR-0009, PO-0004…).

test("full procure-to-pay flow, offline", async ({ page }, testInfo) => {
  const external = blockExternalRequests(page);
  const errors = collectPageErrors(page);
  const badge = page.locator("h1 + span"); // status badge next to the page title

  await test.step("login page offers one-click demo users", async () => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /Meera Joshi/ })).toBeVisible();
    await snap(page, testInfo, "01-login");
  });

  await test.step("requester raises and submits a ₹73,500 PR", async () => {
    await loginAs(page, "Karan Patel");
    await page.getByRole("link", { name: "New request" }).click();
    await page.getByLabel("Justification").fill("Safety kit and packing material for the Bay 3 crew before go-live");
    await page.getByLabel("Item 1").selectOption({ label: "Safety Helmet (pcs)" });
    await page.getByLabel("Quantity 1").fill("50");
    await page.getByLabel("Unit price 1").fill("600");
    await page.getByRole("button", { name: "Add line" }).click();
    await page.getByLabel("Item 2").selectOption({ label: "Packaging Tape (box of 36) (box)" });
    await page.getByLabel("Quantity 2").fill("30");
    await page.getByLabel("Unit price 2").fill("1450");
    await expect(page.getByText("₹73,500.00")).toBeVisible(); // exact preview (lib/decimal.ts)
    await page.getByRole("button", { name: "Save draft" }).click();
    await page.waitForURL(/\/prs\/\d+$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("PR-0009");
    await page.getByRole("button", { name: "Submit for approval" }).click();
    await expect(badge).toHaveText("Pending dept head");
  });
  const prUrl = page.url();

  await test.step("dept head sees the over-budget warning and approves → finance", async () => {
    await switchUser(page, "Neha Iyer");
    await page.getByRole("link", { name: "Approvals" }).click();
    await expect(page.getByRole("link", { name: "PR-0009" })).toBeVisible();
    await page.getByRole("link", { name: "PR-0007" }).click();
    await expect(page.getByText("Over budget", { exact: true })).toBeVisible();
    await snap(page, testInfo, "03-pr-detail-over-budget", true);
    await page.goto(prUrl);
    await page.getByRole("button", { name: "Approve" }).click();
    await page.getByRole("dialog").getByLabel(/Comment/).fill("Needed before Monday's go-live");
    await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
    await expect(badge).toHaveText("Pending finance"); // above the ₹50,000 threshold
  });

  await test.step("finance approves", async () => {
    await switchUser(page, "Priya Nair");
    await expect(page.getByText("Spend vs budget this month")).toBeVisible();
    await snap(page, testInfo, "02-dashboard-finance", true);
    await page.goto(prUrl);
    await page.getByRole("button", { name: "Approve" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
    await expect(badge).toHaveText("Approved");
  });

  await test.step("purchase compares three quotations; a dearer pick needs a reason", async () => {
    await switchUser(page, "Vikram Rao");
    await page.goto(prUrl);
    await page.getByRole("link", { name: "Quotations & PO" }).click();
    const quotes: [string, string, string, string][] = [
      ["Shree Steel & Safety Traders", "560", "1500", "3"], // ₹73,000
      ["Bharat Office Supplies", "590", "1380", "5"], // ₹70,900 — lowest
      ["Techno Solutions Pvt Ltd", "640", "1400", "10"], // ₹74,000
    ];
    for (const [supplier, helmet, tape, days] of quotes) {
      await page.getByRole("button", { name: "Add quotation" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Supplier").selectOption({ label: supplier });
      await dialog.getByLabel("Delivery (days)").fill(days);
      await dialog.getByLabel("Price for Safety Helmet").fill(helmet);
      await dialog.getByLabel("Price for Packaging Tape (box of 36)").fill(tape);
      await dialog.getByRole("button", { name: "Save quotation" }).click();
      await expect(dialog).toBeHidden();
    }
    await expect(page.getByText("Lowest valid total", { exact: true })).toBeVisible();
    await expect(page.getByText("Lowest", { exact: true })).toHaveCount(2); // one per line
    await snap(page, testInfo, "04-quotation-comparison");

    await page.getByRole("button", { name: "Select & create PO" }).first().click(); // Shree
    await expect(page.getByRole("dialog").getByLabel(/Reason for choosing/)).toBeVisible();
    await snap(page, testInfo, "05-select-needs-reason");
    await page.getByRole("dialog").getByRole("button", { name: "Create purchase order" }).click();
    await expect(toast(page)).toContainText("is not the lowest valid one");
    await page.getByRole("dialog").getByLabel(/Reason for choosing/).fill("3-day delivery; Bharat needs 5 days");
    await page.getByRole("dialog").getByRole("button", { name: "Create purchase order" }).click();
    await page.waitForURL(/\/pos\/\d+$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("PO-0004");
    await expect(badge).toHaveText("Issued");
  });
  const poUrl = page.url();

  await test.step("store receives 45 helmets, rejects 5, plus all the tape", async () => {
    await switchUser(page, "Suresh Kumar");
    await page.goto(poUrl);
    await page.getByRole("link", { name: "Record goods receipt" }).click();
    await expect(page.getByLabel("Received Safety Helmet")).toHaveValue("50"); // pre-filled from /receivable
    await page.getByLabel("Received Safety Helmet").fill("45");
    await page.getByLabel("Rejected Safety Helmet").fill("5");
    await page.getByLabel("Rejection reason Safety Helmet").fill("Cracked shells");
    await page.getByRole("button", { name: "Record goods receipt" }).click();
    await page.waitForURL(poUrl);
    await expect(badge).toHaveText("Partially received");
  });

  await test.step("accounts enters the invoice for 50 → MISMATCH with the reason", async () => {
    await switchUser(page, "Anita Desai");
    await page.goto(poUrl);
    await page.getByRole("link", { name: "Enter supplier invoice" }).click();
    await page.getByLabel("Supplier invoice number").fill("SSST/26-27/1102");
    await page.getByLabel("Qty Safety Helmet").fill("50");
    await page.getByRole("button", { name: "Save and run three-way match" }).click();
    await page.waitForURL(/\/invoices\/\d+$/);
    await expect(page.getByText("MISMATCH", { exact: true })).toBeVisible();
    await expect(page.getByText("Safety Helmet: invoiced 50, accepted 40")).toHaveCount(2); // banner + history
    await snap(page, testInfo, "06-invoice-mismatch", true);
  });
  const invoiceUrl = page.url();

  await test.step("late delivery, rematch → MATCHED, pay in two parts → PO closes", async () => {
    await switchUser(page, "Suresh Kumar");
    await page.goto(`${poUrl}/receive`);
    await page.getByRole("button", { name: "Record goods receipt" }).click();
    await page.waitForURL(poUrl);
    await expect(badge).toHaveText("Fully received");

    await switchUser(page, "Anita Desai");
    await page.goto(invoiceUrl);
    await page.getByRole("button", { name: "Rematch" }).click();
    await expect(page.getByText("MATCHED", { exact: true })).toBeVisible();
    await page.getByLabel("Amount (₹)").fill("50000");
    await page.getByLabel("Reference number").fill("UTR-E2E-1");
    await page.getByRole("button", { name: "Record payment" }).click();
    await expect(badge).toHaveText("Partially paid");
    await page.getByLabel("Amount (₹)").fill("99999");
    await page.getByLabel("Reference number").fill("UTR-E2E-2");
    await page.getByRole("button", { name: "Record payment" }).click();
    await expect(toast(page)).toContainText("exceeds the balance due of ₹23,000.00");
    await page.getByLabel("Amount (₹)").fill("23000");
    await page.getByRole("button", { name: "Record payment" }).click();
    await expect(toast(page)).toContainText("PO-0004 is now closed");

    await page.goto(poUrl);
    await expect(badge).toHaveText("Closed");
    await expect(page.getByText("50 / 50 pcs")).toHaveCount(2); // accepted and invoiced bars
    await snap(page, testInfo, "07-po-detail-closed", true);
  });

  expect(external, "requests that left the machine").toEqual([]);
  expect(errors, "browser errors / 5xx responses").toEqual([]);
});

test("buttons follow the API's actions: admin, requester and store", async ({ page }) => {
  const external = blockExternalRequests(page);

  await loginAs(page, "Meera Joshi"); // ADMIN: sees everything, can do nothing
  await page.goto("/prs/7");
  await expect(page.getByText("Over budget", { exact: true })).toBeVisible();
  await expect(page.locator("main button")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Suppliers" })).toBeVisible();

  await switchUser(page, "Arjun Mehta"); // IT head: his own PR waits on finance, no approve button
  await page.goto("/prs/6");
  await expect(page.locator("h1 + span")).toHaveText("Pending finance");
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);

  await switchUser(page, "Riya Sharma"); // IT requester: an Operations PO is simply not there
  await page.goto("/pos/3");
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();

  await switchUser(page, "Suresh Kumar"); // STORE: no purchase requests at all
  await expect(page.getByRole("link", { name: /requests/i })).toHaveCount(0);
  await page.goto("/prs");
  await expect(page.getByRole("heading", { name: "No access" })).toBeVisible();
  await expect(page.getByRole("main").getByText(/you are STORE/)).toBeVisible(); // the API's own message

  expect(external).toEqual([]);
});

test("API docs load with no internet", async ({ page }) => {
  const external = blockExternalRequests(page);
  await page.goto(`${E2E_API}/docs`);
  await expect(page.locator(".swagger-ui .info .title")).toContainText("Purchase Management System");
  await expect(page.getByText("/api/prs/{pr_id}/approve")).toBeVisible();
  expect(external).toEqual([]);
});
