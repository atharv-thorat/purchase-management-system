import path from "node:path";

import { expect, type Page, type TestInfo } from "@playwright/test";

/** Every request must stay on this machine: proves the app runs with no internet. */
export function blockExternalRequests(page: Page): string[] {
  const external: string[] = [];
  void page.route("**/*", (route) => {
    const { hostname, protocol } = new URL(route.request().url());
    if (protocol === "data:" || protocol === "blob:" || hostname === "localhost" || hostname === "127.0.0.1") {
      return route.continue();
    }
    external.push(route.request().url());
    return route.abort();
  });
  return external;
}

/** Collect browser errors, ignoring the API's deliberate 4xx answers the test provokes. */
export function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("response", (r) => r.status() >= 500 && errors.push(`HTTP ${r.status()} ${r.url()}`));
  return errors;
}

export async function loginAs(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Welcome");
}

/** The header's "switch demo user" menu, exactly as it's used in the live demo. */
export async function switchUser(page: Page, name: string) {
  await page.getByRole("banner").locator("button[aria-expanded]").click();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByRole("banner")).toContainText(name);
}

/** One entry of a status history, found by its title ("Approved by finance"). */
export function timelineEntry(page: Page, title: string) {
  return page.getByTestId("timeline-entry").filter({ has: page.getByText(title, { exact: true }) });
}

export function toast(page: Page) {
  return page.locator(".fixed [role='status'], .fixed [role='alert']").last();
}

/** With UPDATE_SCREENSHOTS=1 the README screenshots in docs/screenshots are regenerated. */
export async function snap(page: Page, testInfo: TestInfo, name: string, fullPage = false) {
  await page.waitForTimeout(250);
  const style = "[aria-live] { display: none !important; }"; // keep transient toasts out of screenshots
  const shot = await page.screenshot({ fullPage, style });
  await testInfo.attach(name, { body: shot, contentType: "image/png" });
  if (process.env.UPDATE_SCREENSHOTS) {
    const file = path.resolve(__dirname, "../../docs/screenshots", `${name}.png`);
    await page.screenshot({ path: file, fullPage, style });
  }
}
