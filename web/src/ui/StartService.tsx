/** How to start the Python planning service, for Windows and for macOS / Linux. Sits inside a `.offline` box. */
export function StartCommands() {
  return (
    <>
      <p style={{ marginTop: "0.6rem" }}>Windows:</p>
      <code>.venv\Scripts\python -m uvicorn api.server:app --port 8000</code>
      <p style={{ marginTop: "0.6rem" }}>macOS / Linux:</p>
      <code>.venv/bin/python -m uvicorn api.server:app --port 8000</code>
      <p className="note">
        Or run <b>npm run api</b> in the <b>web</b> folder, which picks the right one.
      </p>
    </>
  );
}
