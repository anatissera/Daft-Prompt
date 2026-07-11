export const dynamic = "force-dynamic";

export async function POST() {
  return Response.json(
    {
      detail: (
        "User-uploaded local audio analysis is not a supported Daft Prompt path. "
        + "Ask about a song, artist, album, or genre so Daft Prompt can use public evidence "
        + "connectors such as Songsterr, tab/chord pages, and metadata sources."
      ),
    },
    { status: 410 },
  );
}
