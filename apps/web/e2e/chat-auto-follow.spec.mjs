import { test, expect } from "@playwright/test";

async function send(page, message) {
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(message);
  await input.press("Enter");
}

async function metrics(page) {
  return page.getByTestId("chat-thread").evaluate((element) => ({
    scrollTop: element.scrollTop,
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
    distance: element.scrollHeight - element.scrollTop - element.clientHeight,
  }));
}

test("conversation follows sends and responses without overriding manual upward scrolling", async ({ page }) => {
  await page.route("**/api/chat", async (route) => {
    const body = route.request().postDataJSON();
    if (String(body.message).includes("delayed")) {
      await new Promise((resolve) => setTimeout(resolve, 900));
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ intent: "clarify", reply: `Assistant response for ${body.message}` }),
    });
  });
  await page.goto("/");
  await expect(page.getByText(/Daft Prompt — multi-agent music studio/)).toBeVisible();

  for (let index = 0; index < 9; index += 1) {
    await send(page, `message ${index} with enough text to grow the conversation`);
    await expect(page.locator(".chat-message-assistant")).toHaveCount(index + 2);
  }
  expect((await metrics(page)).distance).toBeLessThanOrEqual(2);

  await send(page, "delayed response while I read above");
  await expect(page.locator(".chat-message-system")).toHaveCount(1);
  await page.getByTestId("chat-thread").evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event("scroll"));
  });
  await expect(page.locator(".chat-message-assistant")).toHaveCount(11);
  expect((await metrics(page)).scrollTop).toBeLessThan(20);

  await send(page, "resume follow");
  await expect(page.locator(".chat-message-assistant")).toHaveCount(12);
  expect((await metrics(page)).distance).toBeLessThanOrEqual(2);

  const latest = page.locator(".chat-message-assistant").last();
  const composer = page.locator(".chat-composer");
  const latestBox = await latest.boundingBox();
  const composerBox = await composer.boundingBox();
  expect(latestBox).not.toBeNull();
  expect(composerBox).not.toBeNull();
  expect(latestBox.y + latestBox.height).toBeLessThanOrEqual(composerBox.y + 1);
});
