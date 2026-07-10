import { test, expect } from "@playwright/test";

const meaningfulTab = {
  instrument: "guitar",
  track_name: "Lead guitar",
  tuning: ["E2", "A2", "D3", "G3", "B3", "E4"],
  summary: "Measures 5–8 with playable guitar notes.",
  answer: "Here is the requested guitar tab.",
  measures: [{
    index: 4,
    marker: "Verse",
    events: [{ beat_index: 1, string: 2, fret: 3, pitch: 62, duration: "quarter", rest: false }],
  }],
};

async function send(page, message) {
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(message);
  await input.press("Enter");
}

test("tab requests visibly render musical content and explicit failures", async ({ page }) => {
  await page.route("**/api/chat", async (route) => {
    const body = route.request().postDataJSON();
    const failed = String(body.message).includes("unavailable");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        intent: "answer",
        reply: failed ? "I could not render piano tablature for this source." : meaningfulTab.answer,
        tab_excerpt: failed ? {
          instrument: "piano",
          tuning: [],
          measures: [],
          summary: "No compatible tab source is available.",
          answer: "I could not render piano tablature for this source.",
          error: "tab_source_unavailable",
        } : meaningfulTab,
      }),
    });
  });
  await page.goto("/");

  await send(page, "Show me guitar tab");
  const tab = page.getByRole("region", { name: "guitar tab excerpt" });
  await expect(tab).toBeVisible();
  await expect(tab).toContainText("string 2 · fret 3");
  await expect(tab).toContainText("Measures 5–8");

  await send(page, "Show unavailable piano tab");
  const failure = page.getByRole("alert", { name: "Tab unavailable" });
  await expect(failure).toBeVisible();
  await expect(failure).toContainText("could not render piano tablature");
});
