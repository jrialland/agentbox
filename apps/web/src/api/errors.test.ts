import { ApiError, toApiError } from "./errors";

test("normalizes a string detail", () => {
  const error = toApiError({ detail: "Session not found" }, "fallback", 404);
  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(404);
  expect(error.detail).toBe("Session not found");
});

test("normalizes validation arrays into fields", () => {
  const error = toApiError(
    {
      detail: [
        { loc: ["body", "name"], msg: "name is required" },
        { loc: ["body", "path"], msg: "path must be a directory" },
      ],
    },
    "fallback",
    422,
  );
  expect(error.fields).toEqual({
    name: "name is required",
    path: "path must be a directory",
  });
});

test("normalizes network failures", () => {
  const error = toApiError(new TypeError("fetch failed"), "Network unavailable");
  expect(error.status).toBe(0);
  expect(error.detail).toBe("Network unavailable");
});
