import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false;
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });
}
