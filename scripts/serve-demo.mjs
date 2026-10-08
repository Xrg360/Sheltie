// Minimal static server for the demo export: serves ./out at /demo (like GitHub Pages will).
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../out", import.meta.url));
const port = Number(process.env.PORT || 4173);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json", ".txt": "text/plain", ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json" };

createServer((request, response) => {
  const url = new URL(request.url || "/", "http://localhost");
  if (!url.pathname.startsWith("/demo")) {
    response.writeHead(302, { Location: "/demo/" }).end();
    return;
  }
  let path = normalize(join(root, decodeURIComponent(url.pathname.slice("/demo".length))));
  if (!path.startsWith(root)) return void response.writeHead(403).end();
  if (existsSync(path) && statSync(path).isDirectory()) path = join(path, "index.html");
  if (!existsSync(path)) path = join(root, "404.html");
  response.writeHead(path.endsWith("404.html") && !url.pathname.endsWith("404.html") ? 404 : 200, { "Content-Type": types[extname(path)] || "application/octet-stream" });
  createReadStream(path).pipe(response);
}).listen(port, () => console.log(`Demo on http://localhost:${port}/demo/`));
