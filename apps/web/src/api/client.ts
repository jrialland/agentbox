import createClient from "openapi-fetch";

import { API_URL } from "../config";
import { useAuthStore } from "../store/auth";
import type { paths } from "./schema";

export function authMiddleware(getToken: () => string | null) {
  return {
    onRequest({ request }: { request: Request }) {
      const token = getToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };
}

export const api = createClient<paths>({
  baseUrl: API_URL,
});

api.use(authMiddleware(() => useAuthStore.getState().token));

api.use({
  onResponse({ response }) {
    if (response.status === 401) {
      useAuthStore.getState().clear();
    }
  },
});
