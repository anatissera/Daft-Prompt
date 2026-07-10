import { readFile } from "node:fs/promises";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

export async function GET() {
  let frontend = "development-worktree";
  try {
    const parsed = JSON.parse(await readFile("/app/build-info.json", "utf8")) as { commit?: string };
    if (parsed.commit) frontend = parsed.commit;
  } catch {
    // A host-side development server has no image build metadata.
  }
  let backend = "unavailable";
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
    const parsed = (await response.json()) as { commit?: string };
    if (parsed.commit) backend = parsed.commit;
  } catch {
    // The visible identifier should still report the frontend build.
  }
  return Response.json({ frontend, backend });
}
