export interface TabAsciiRendererExcerpt {
  instrument?: string;
  tuning?: string[];
  measures?: Array<{
    index: number;
    marker?: string | null;
    events: Array<{
      beat_index: number;
      duration?: string;
      string?: number | null;
      fret?: number | null;
      rest?: boolean;
    }>;
  }>;
}

export function renderTabAscii(excerpt: TabAsciiRendererExcerpt): string;
