import { useAuthStore } from "./auth";

beforeEach(() => {
  sessionStorage.clear();
  useAuthStore.getState().clear();
});

test("sets token and user", () => {
  useAuthStore.getState().setToken("abc");
  useAuthStore.getState().setUser({ id: "u1", username: "alice", permissions: ["x"] });
  expect(useAuthStore.getState().token).toBe("abc");
  expect(useAuthStore.getState().user?.username).toBe("alice");
});

test("persists to sessionStorage", () => {
  useAuthStore.getState().setToken("abc");
  expect(sessionStorage.getItem("agentbox-auth")).toContain("abc");
});

test("clear resets token and user", () => {
  useAuthStore.getState().setToken("abc");
  useAuthStore.getState().clear();
  expect(useAuthStore.getState().token).toBeNull();
  expect(useAuthStore.getState().user).toBeNull();
});
