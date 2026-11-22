import { readFileSync } from "node:fs";
import { join } from "node:path";

interface FontFace {
  file: string;
  family: string;
  weight: string;
}

const FACES: FontFace[] = [
  { file: "Silkscreen-Regular.woff2", family: "Silkscreen", weight: "400" },
  { file: "Inter-Regular.woff2", family: "Inter", weight: "400" },
  { file: "Inter-SemiBold.woff2", family: "Inter", weight: "600" },
  { file: "JetBrainsMono-Regular.woff2", family: "JetBrains Mono", weight: "400" },
];

export function buildFontCss(fontsDir: string): string {
  return FACES.map((face) => {
    const base64 = readFileSync(join(fontsDir, face.file)).toString("base64");
    return `@font-face{font-family:"${face.family}";font-style:normal;font-weight:${face.weight};font-display:block;src:url(data:font/woff2;base64,${base64}) format("woff2");}`;
  }).join("\n");
}
