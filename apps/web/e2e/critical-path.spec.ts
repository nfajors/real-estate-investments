import { expect, test } from "@playwright/test";

/**
 * PRD §5 critical path: create workspace → deal → documents → verify → underwrite →
 * scenarios → export → analyst. Uses the seeded, clearly-labelled demo portfolio.
 */
test("critical underwriting workflow", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const tab = (name: string) => page.getByRole("navigation", { name: "Deal sections" }).getByRole("link", { name, exact: true });

  // 1. Register a workspace with demo data
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Avery Analyst");
  await page.getByLabel("Firm / organization").fill("E2E Capital Partners");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill("e2e-Password-123");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("heading", { name: "Investment Dashboard" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("fictional demo data")).toBeVisible();
  await expect(page.getByText("Wtd. avg cap rate")).toBeVisible();

  // 2. Open the demo multifamily deal
  await page.getByRole("link", { name: "Deals", exact: true }).click();
  await page.getByRole("link", { name: "Harbor Point Residences" }).first().click();
  await expect(page.getByRole("heading", { name: "Harbor Point Residences" })).toBeVisible();
  await expect(page.getByText("Levered IRR").first()).toBeVisible();

  // 3. Verify AI/rule-extracted data in the split view
  await tab("Documents").click();
  await expect(page.getByText("Harbor-Point-OM-SAMPLE.pdf")).toBeVisible();
  await page.getByRole("row", { name: /Harbor-Point-OM-SAMPLE\.pdf/ }).getByRole("link", { name: "Review" }).click();
  await expect(page.getByText("Asking / purchase price")).toBeVisible();
  await page.getByText("Asking / purchase price").click();
  await expect(page.getByLabel("Highlighted source")).toBeVisible();
  await page.getByRole("button", { name: "Accept verified" }).click();
  await expect(page.getByText(/Accepted \d+ fields/)).toBeVisible();

  // 4. Apply verified data to the base case
  await tab("Documents").click();
  await page.getByRole("button", { name: "Apply verified data to base case" }).click();
  await expect(page.getByText(/Applied \d+ verified fields/)).toBeVisible();

  // 5. Edit an assumption, see the live recalculation, save
  await tab("Underwriting").click();
  await expect(page.getByText("Saved · matches stored snapshot")).toBeVisible();
  const vacancy = page.getByLabel("Vacancy", { exact: true });
  await vacancy.fill("8");
  await expect(page.getByText("Unsaved changes · live preview")).toBeVisible();
  await expect(page.getByText(/Live preview computed in/)).toBeVisible();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Assumptions saved/)).toBeVisible();

  // 6. Sensitivity table
  await tab("Scenarios & Risk").click();
  await page.getByRole("button", { name: "Run table" }).click();
  await expect(page.locator("table td").first()).toBeVisible();

  // 7. Export the Excel model
  await tab("Reports").click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /Excel/i }).first().click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);

  // 8. Ask the analyst
  await tab("AI Analyst").click();
  await page.getByLabel("Message the analyst").fill("What is the DSCR and the main risks?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/DSCR/).last()).toBeVisible({ timeout: 30_000 });

  // 9. Compare deals
  await page.getByRole("link", { name: "Compare", exact: true }).click();
  await expect(page.getByText("Levered IRR").first()).toBeVisible();
});
