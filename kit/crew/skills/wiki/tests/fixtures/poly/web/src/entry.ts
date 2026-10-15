import * as m from "./math.js";
import Widget, { Base as B } from "./widget.js";
import { greet } from "./y";
import fs from "node:fs";
import { fmt } from "../../tools/fmt/src/fmt.js";
import { helper } from "./lib";
export { greet as hello } from "./y";

/** Start the app. */
export async function start(): Promise<string> {
  const lazy = await import("./lazy");
  const w = new Widget("#app");
  const label = `total: ${m.mul(2, `${m.add(1, 2)}`.length)}`;
  const res = await fetch("/v1/latest");
  fs.existsSync("/tmp");
  return fmt(label) + w.render() + lazy.later() + greet() + helper() + String(res.ok) + String(B);
}
