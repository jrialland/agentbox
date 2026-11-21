import path from "node:path";

const root = path.resolve(import.meta.dir, "../storybook-static");
const port = Number(process.env.PORT ?? 6006);

const server = Bun.serve({
  port,
  async fetch(request) {
    const url = new URL(request.url);
    const pathname = decodeURIComponent(url.pathname);
    const relative = pathname === "/" ? "index.html" : pathname.slice(1);
    const filePath = path.resolve(root, relative);
    if (!filePath.startsWith(root)) {
      return new Response("Forbidden", { status: 403 });
    }
    const file = Bun.file(filePath);
    if (!(await file.exists())) {
      return new Response("Not found", { status: 404 });
    }
    return new Response(file);
  },
});

console.log(`Storybook static preview: http://localhost:${server.port}`);
