const server = Bun.serve({
  port: 9999,
  fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/models") {
      return Response.json({ object: "list", data: [{ id: "e2e-model" }] });
    }
    return new Response("not found", { status: 404 });
  },
});
console.log(`stub models server on ${server.port}`);
