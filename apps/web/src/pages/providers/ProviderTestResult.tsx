import type { ProviderTestResult } from "../../api/endpoints";
import { Badge } from "../../design-system/primitives/Badge";
import { StatusChip } from "../../design-system/primitives/StatusChip";

export function ProviderTestResultView({
  result,
}: {
  result: ProviderTestResult;
}) {
  if (!result.ok) {
    return (
      <div role="status" style={{ display: "grid", gap: 6 }}>
        <StatusChip tone="danger">connection failed</StatusChip>
        <span>{result.error?.message ?? "The connection test failed."}</span>
      </div>
    );
  }

  return (
    <div role="status" style={{ display: "grid", gap: 6 }}>
      <StatusChip tone="success">connected</StatusChip>
      <span>
        Connected — {result.model_count ?? 0} models in {result.latency_ms}ms
      </span>
      {result.sample_models.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {result.sample_models.map((model) => (
            <Badge key={model} tone="neutral">
              {model}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
