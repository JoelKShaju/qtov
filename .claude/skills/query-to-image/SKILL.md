---
name: query-to-image
description: Run a natural-language clinical-trials query against the running app and show the resulting chart as an image inline in the chat. Use when asked to "show / visualize / render / preview the graph (or chart) for <query>".
---

# Query → chart image

Renders the visualization a query produces as a PNG and displays it directly in the chat.

## Prereqs
- The stack is running (`make up`, or the observability overlay) — backend at http://localhost:8000.
  If it isn't, start it first.

## Steps
1. Render the chart (matplotlib + networkx are pulled ephemerally by `uv --with`, so nothing is
   added to the project deps). Run from the `backend` dir so the project's `httpx` is available.
   Write to a unique tmp file so renders don't clobber each other:
   ```
   cd backend && uv run --with matplotlib --with networkx python ../scripts/render_query.py "<QUERY>" "/tmp/qtov_chart_$(date +%s).png"
   ```
   - Success → it prints `WROTE <absolute-path>`. **Capture that exact path.**
   - Unsupported query → it prints `UNSUPPORTED:` and the supported query types; relay that to the
     user instead of an image.
   - Set `API_BASE` if the backend isn't on `localhost:8000`.
2. **Read** the written path (use the Read tool) so the chart renders inline for clients that show
   image tool-results.
3. **Always tell the user the absolute file path** (the `WROTE` line) in your reply — e.g.
   "Saved to `/tmp/qtov_chart_1719371234.png` (open with `open <path>`)" — so they can view it even
   if the inline preview doesn't render in their client.
4. Briefly summarize what the chart shows, and note the live interactive version is at
   http://localhost:5173.

## Notes
- Supports `line`, `bar`, `grouped_bar`, `network`, and `scatter` charts — mirrors the frontend's
  ECharts output.
- For time-trend (`line`) charts, an in-progress/projected-year caveat is printed under the chart
  when present (the latest/future years are incomplete and shouldn't be read as a decline).
- The image is a static snapshot; for click-to-trace citations use the web UI.
