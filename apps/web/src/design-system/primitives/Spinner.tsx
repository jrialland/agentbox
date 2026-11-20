import { Loader } from "@mantine/core";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" aria-label={label}>
      <Loader size="sm" color="phosphor" />
    </span>
  );
}
