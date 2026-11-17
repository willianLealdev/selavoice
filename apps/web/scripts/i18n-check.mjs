// Confere se todo texto usado em t("...") tem tradução em lib/dict.ts. Uso: npm run i18n:check
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? (f === "node_modules" || f === ".next" ? [] : walk(p)) : [p]; });
const dict = readFileSync("lib/dict.ts", "utf8");
const STR = /"((?:[^"\\]|\\.)*)"/;
const have = new Set([...dict.matchAll(/^\s*"((?:[^"\\]|\\.)*)":\s*\[/gm)].map((m) => m[1]));
const missing = new Set();
for (const f of [...walk("app"), ...walk("lib")].filter((p) => /\.tsx$/.test(p) && !p.endsWith("i18n.tsx"))) {
  const s = readFileSync(f, "utf8");
  for (const m of s.matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"/g)) if (!have.has(m[1])) missing.add(m[1]);
  for (const name of ["FEATURES", "FAQ", "HELP", "DOCS", "STATUS"]) {
    const i = s.search(new RegExp(`const ${name}\\b`)); if (i < 0) continue;
    // trecho da tabela: até o primeiro "];" ou "};" depois do começo (cobre tabelas indentadas ou de uma linha)
    const ends = [s.indexOf("];", i + 20), s.indexOf("};", i + 20)].filter((x) => x > 0);
    const seg = s.slice(i, Math.min(...ends));
    for (const m of seg.matchAll(/"((?:[^"\\]|\\.)*)"/g)) if ((m[1].includes(" ") || /^[A-ZÁÉÍÓÚ]/.test(m[1])) && !have.has(m[1])) missing.add(m[1]);
  }
}
if (missing.size) { console.log("Faltam traduções:\n" + [...missing].map((x) => " - " + x).join("\n")); process.exit(1); }
console.log(`OK: ${have.size} textos traduzidos, nenhum faltando.`);
