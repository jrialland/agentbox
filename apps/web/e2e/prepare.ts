import { rm } from "node:fs/promises";
import path from "node:path";

const dbPath = path.resolve(import.meta.dir, "../../../e2e.db");
await rm(dbPath, { force: true });
await rm(path.resolve(import.meta.dir, "../../../e2e-skills"), {
  recursive: true,
  force: true,
});
await rm(path.resolve(import.meta.dir, "../../../e2e-media"), {
  recursive: true,
  force: true,
});
console.log(`removed ${dbPath} (if present)`);
