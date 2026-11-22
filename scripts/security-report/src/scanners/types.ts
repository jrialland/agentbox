import type {
  Finding,
  MaintenanceIssue,
} from "../model";
import type { JsComponent } from "../project";

export interface ScanContext {
  root: string;
  pythonRoots: string[];
  jsComponents: JsComponent[];
  includeTests: boolean;
  extraExcludes: string[];
  timeoutMs: number;
  versions: Record<string, string>;
}

export interface ParsedScanner {
  findings: Finding[];
  stats: Record<string, number | string>;
  warnings: string[];
  errors: string[];
  partial: boolean;
  maintenance: MaintenanceIssue[];
}
