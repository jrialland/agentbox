import { useAuthStore } from "./auth";

test("auth store sets and clears token", () => {
  useAuthStore.getState().setToken("abc");
  expect(useAuthStore.getState().token).toBe("abc");
  useAuthStore.getState().clear();
  expect(useAuthStore.getState().token).toBeNull();
});
