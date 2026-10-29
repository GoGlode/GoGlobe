import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { globSync } from "node:fs";
import test from "node:test";

test("production bundle keeps API paths relative when VITE_API_URL is unset", () => {
  const files = globSync("dist/assets/*.js");
  assert.ok(files.length > 0, "run npm run build before this regression test");
  const bundle = files.map((file) => readFileSync(file, "utf8")).join("\n");

  assert.doesNotMatch(bundle, /undefined\/api\/v1/);
  assert.match(bundle, /\/api\/v1\/session/);
  assert.match(bundle, /\/api\/v1\/searches/);
});
