import { ApiError } from "./errors";
import { shouldRetry } from "./queryClient";

test("retries 5xx once and never retries 4xx", () => {
  expect(shouldRetry(0, new ApiError("boom", 500))).toBe(true);
  expect(shouldRetry(1, new ApiError("boom", 500))).toBe(false);
  expect(shouldRetry(0, new ApiError("missing", 404))).toBe(false);
});
