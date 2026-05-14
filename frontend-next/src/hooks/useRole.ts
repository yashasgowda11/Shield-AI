"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { type Role } from "@/lib/roles";

interface RoleStore {
  role: Role;
  setRole: (r: Role) => void;
}

// Install zustand: npm install zustand
// Falls back to localStorage so role persists across page refreshes
export const useRole = create<RoleStore>()(
  persist(
    (set) => ({
      role: "Procurement Analyst",
      setRole: (role) => set({ role }),
    }),
    { name: "shield-ai-role" }
  )
);
