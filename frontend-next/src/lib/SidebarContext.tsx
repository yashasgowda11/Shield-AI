"use client";

import { createContext, useContext } from "react";

interface SidebarContextType {
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const SidebarContext = createContext<SidebarContextType>({
  open: false,
  setOpen: () => {},
});

export const useSidebar = () => useContext(SidebarContext);
