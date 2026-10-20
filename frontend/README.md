# TRUSTLENS Frontend

A modern React 18 + TypeScript single-page application built with TailwindCSS and bundled with Webpack. It connects to the TRUSTLENS FastAPI loopback forensics backend.

## Prerequisites

- **Node.js**: v18 or newer
- **npm**: v9 or newer

## Commands

From this directory (`frontend/`):

### 1. Install Dependencies
```bash
npm install
```

### 2. Build for Production
Compiles TypeScript, processes Tailwind CSS, and outputs the production bundle (`bundle.js`) to `frontend/static/`:
```bash
npm run build
```

### 3. Run Development Server
Starts the Webpack Dev Server on `http://localhost:3000` with hot-module reloading and automatic `/api` proxy to the local backend on `http://127.0.0.1:8765`:
```bash
npm run dev
# or
npm start
```

### 4. Run Tests
Runs the Jest test suite with jsdom and React Testing Library:
```bash
npm test
```

### 5. Lint and Typecheck
```bash
npm run lint
npm run format:check
```

## Directory Structure
- `src/` — React UI components, views, state context, and API client.
- `static/` — HTML entry point (`index.html`), static stylesheets, and built bundles (`bundle.js`).
- `scripts/` — Helper scripts.
- `webpack.config.js` — Webpack bundling and dev-server configuration.
- `tailwind.config.js` — TailwindCSS styling configuration.
