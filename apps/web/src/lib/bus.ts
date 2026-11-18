import mitt, { type Emitter } from "mitt";

export type AppEvents = {
  "theme:changed": { scheme: "light" | "dark" };
};

export const bus: Emitter<AppEvents> = mitt<AppEvents>();
