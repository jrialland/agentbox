import { describe, expect, test } from "bun:test";
import { parseBunAudit, parseNpmAudit } from "./bun-audit";

const bunJson = {
  zod: [
    {
      id: 1243066,
      url: "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5",
      title: "Zod memory exhaustion",
      severity: "high",
      vulnerable_versions: "<4.6.6",
      cwe: ["CWE-770"],
      cvss: { score: 7.5, vectorString: "CVSS:3.1/..." },
    },
  ],
};

const npmJson = {
  vulnerabilities: {
    react: {
      name: "react",
      severity: "moderate",
      isDirect: true,
      via: [
        {
          source: 123,
          name: "react",
          title: "React issue",
          url: "https://example.com/react",
          severity: "moderate",
          range: "<19.0.0",
          cvss: { vectorString: "CVSS:3.1/..." },
        },
      ],
      range: "<19.0.0",
      nodes: ["node_modules/react"],
      fixAvailable: { name: "react", version: "19.0.0", isSemVerMajor: false },
    },
  },
};

describe("parseBunAudit", () => {
  test("normalizes advisories and installed versions", () => {
    const parsed = parseBunAudit(bunJson, { zod: "4.0.0" });
    expect(parsed.findings).toHaveLength(1);
    expect(parsed.findings[0]?.severity).toBe("high");
    expect(parsed.findings[0]?.packageName).toBe("zod");
    expect(parsed.findings[0]?.installedVersion).toBe("4.0.0");
    expect(parsed.findings[0]?.vulnerableRange).toBe("<4.6.6");
    expect(parsed.stats.affectedPackages).toBe(1);
  });
});

describe("parseNpmAudit", () => {
  test("normalizes advisories and fixes", () => {
    const parsed = parseNpmAudit(npmJson, { react: "18.0.0" });
    expect(parsed.findings).toHaveLength(1);
    expect(parsed.findings[0]?.severity).toBe("medium");
    expect(parsed.findings[0]?.installedVersion).toBe("18.0.0");
    expect(parsed.findings[0]?.fix).toBe("Upgrade react to 19.0.0");
  });
});
