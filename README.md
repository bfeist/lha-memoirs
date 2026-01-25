# Lindy Achen Memoirs

A digital archive of the voice memoirs of Linden "Lindy" Hilary Achen (1902–1994). This project preserves and presents his oral history, recounting life in the early 20th century, from his childhood in Iowa to pioneer life in Saskatchewan and his career bringing electricity to rural communities.

## About Lindy Achen

**Linden "Lindy" Hilary Achen** was born on October 7, 1902, in Remsen, Iowa. In 1907, at the age of four, his family immigrated to Saskatchewan, Canada, settling near Halbright during the great wave of prairie pioneers.

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

## Data Processing

The audio processing pipeline (transcription, alignment, and analysis) is handled by a set of Python scripts.

For detailed documentation on the data processing workflow, see [scripts/README.md](scripts/README.md).

## Research Notes

Original inventory notes on the physical tapes can be found in [docs/tape_inventory.md](docs/tape_inventory.md).
