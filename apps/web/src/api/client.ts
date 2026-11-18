import createClient from "openapi-fetch";

import type { paths } from "./schema";

export function authMiddleware(token: string | null) {
  return {
    onRequest({ request }: { request: Request }) {
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };
}

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

api.use(authMiddleware(null));
