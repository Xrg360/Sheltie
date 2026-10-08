import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const PAGES = [
  { path: "", heading: /problems? need|All systems normal/ },
  { path: "incidents/", heading: /events? recorded/ },
  { path: "monitors/", heading: /sites up/ },
  { path: "containers/", heading: /containers running/ },
  { path: "network/", heading: /Online|unreachable/ },
  { path: "host/", heading: /healthy|running high/ },
  { path: "settings/", heading: /Preferences/ },
];

test.describe("every page answers first and is accessible", () => {
  for (const { path, heading } of PAGES) {
    test(`/${path}`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(path);
      // DESIGN.md invariant 1: the page leads with an answer sentence.
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      const serious = results.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical");
      expect(serious.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
      expect(errors).toEqual([]);
    });
  }
});

test("command palette searches and navigates", async ({ page, isMobile }) => {
  await page.goto("");
  const input = page.getByRole("combobox");
  // The shortcut and the button only work once React has hydrated, which can lag behind the first
  // paint on a busy CI runner. Retry until the palette opens, but only while it is still closed:
  // Ctrl+K toggles, so pressing it again on an open palette would close it.
  await expect(async () => {
    if (!(await input.isVisible())) {
      if (isMobile) await page.getByRole("button", { name: "Search or run a command" }).click();
      else await page.keyboard.press("Control+k");
    }
    await expect(input).toBeFocused({ timeout: 1_000 });
  }).toPass({ timeout: 10_000 });
  await input.fill("network");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/network\/?$/);
});

test("problems offer a next step, and restarting asks for confirmation", async ({ page }) => {
  await page.goto("");
  const attention = page.locator("section", { has: page.getByRole("heading", { name: "Needs attention" }) });
  await expect(attention.getByRole("heading", { name: "Blog is down" })).toBeVisible();
  await attention.getByRole("button", { name: "Start" }).click();
  const dialog = page.getByRole("dialog", { name: "Restart blog?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("All systems normal");
});

test("adding a monitor suggests a name and validates the address", async ({ page }) => {
  await page.goto("monitors/?add=1");
  const sheet = page.getByRole("dialog", { name: "Add a monitor" });
  await sheet.getByLabel("Address").fill("not a url");
  await sheet.getByRole("button", { name: "Start monitoring" }).click();
  await expect(sheet.getByText("Enter an address that starts with http:// or https://")).toBeVisible();
  await sheet.getByLabel("Address").fill("https://git.home.example");
  await expect(sheet.getByLabel("Name")).toHaveValue("Git");
  await sheet.getByRole("button", { name: "Start monitoring" }).click();
  await expect(page.getByText("Monitoring Git")).toBeVisible();
});

test("silencing alerts shows in the top bar", async ({ page }) => {
  await page.goto("");
  await page.getByRole("button", { name: /Alerts on/ }).click();
  await page.getByRole("menuitem", { name: "Silence for 1 hour" }).click();
  await expect(page.getByRole("button", { name: /Silenced/ })).toBeVisible();
});
