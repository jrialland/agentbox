import { createContext, useContext, useState, type ReactNode } from "react";

import type { HelpId } from "./types";
import { HelpDrawer } from "./HelpDrawer";

const HelpContext = createContext<{ openHelp: (id: HelpId) => void } | null>(null);

export function HelpProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<HelpId | null>(null);
  return (
    <HelpContext.Provider value={{ openHelp: setActive }}>
      {children}
      <HelpDrawer active={active} onClose={() => setActive(null)} />
    </HelpContext.Provider>
  );
}

export function useHelp() {
  const context = useContext(HelpContext);
  if (!context) throw new Error("useHelp must be used inside HelpProvider");
  return context;
}
