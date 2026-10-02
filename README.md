# Lindy Achen Memoirs

A digital archive of the voice memoirs of Linden "Lindy" Hilary Achen (1902–1994). This project preserves and presents his oral history, recounting life in the early 20th century, from his childhood in Iowa to pioneer life in Saskatchewan and his career bringing electricity to rural communities.

## About Lindy Achen

**Linden "Lindy" Hilary Achen** was born on October 7, 1902, in Remsen, Iowa. In 1907, at the age of four, his family immigrated to Saskatchewan, Canada, settling near Halbrite during the great wave of prairie pioneers.

Lindy's memoirs capture a vivid picture of the era:

- **Pioneer Life:** Farming with horse teams, surviving the 1918 flu pandemic, and early prairie settlements.
- **Career:** Challenging work as a power lineman and construction foreman across Western Canada and the US Midwest (1920s–1960s).
- **Family History:** Detailed recollections of the Achen family recorded in the 1980s.

## Project Features

This application provides an interactive way to explore the recordings:

- **Audio Playback:** Listen to the original memoir tapes, digitized and restored.
- **Interactive Transcripts:** Read along with time-synced transcripts.
- **Search:** Find specific stories and topics within the hours of recordings.
- **Chapters & Stories:** Chapter markers of individual anecdotes.
- **LHA-GPT:** Chat with a RAG-powered AI assistant to ask questions about Lindy's life and stories.
- **Travel Map:** Explore geographic context with places Lindy mentions and visualize his journey.
- **Alternate Tellings:** Discover how Lindy recounted the same stories differently across different memoirs.

## Running the Project

This is a modern web application built with React, Vite, and TanStack Query.

### Prerequisites

- Node.js (v22 recommended)
- npm

### Development

To start the development server:

```bash
npm install
npm run dev
```

The application will be available at `http://localhost:5173`.

### Build

To build for production:

```bash
npm run build
```

### Map tiles

The Places map uses CARTO Positron tiles. CARTO now requires a basemap API key;
requests without one display an "API KEY REQUIRED" watermark.

1. Request a key at [CARTO Basemaps](https://www.carto.com/basemaps/apikey/).
2. Copy `.env.example` to `.env.local` and set `VITE_CARTO_BASEMAP_API_KEY`.
3. Restart the development server after changing the key.

For production, add the GitHub Actions repository secret `VITE_CARTO_BASEMAP_API_KEY`
and rebuild/deploy. Vite embeds this value during the build; setting it only on the
hosting server does not update an existing build. This is a browser-visible basemap
key; configure allowed-site restrictions in CARTO for the production domain and any
development origins you use. Keep the existing CARTO/OpenStreetMap attribution visible.

## Data Processing

The audio processing pipeline (transcription, alignment, and analysis) is handled by a set of Python scripts.

For detailed documentation on the data processing workflow, see [scripts/README.md](scripts/README.md).

## Research Notes

Original inventory notes on the physical tapes can be found in [docs/tape_inventory.md](docs/tape_inventory.md).
