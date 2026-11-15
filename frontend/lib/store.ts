import { create } from "zustand";

export interface User {
  id: number;
  email: string;
  name: string;
  role: "admin" | "approver" | "faculty" | "student" | "security";
  scopes: string[];
  dept: string | null;
  ref_id: number | null;
}

interface AuthState {
  token: string | null;
  user: User | null;
  ready: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  hydrate: () => void;
}

const STORAGE_KEY = "campusflow-auth";

function load(): { token: string; user: User } | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function save(value: { token: string; user: User } | null): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    return;
  }
}

export const useAuth = create<AuthState>((set) => ({
  token: null,
  user: null,
  ready: false,
  login: (token, user) => {
    save({ token, user });
    set({ token, user, ready: true });
  },
  logout: () => {
    save(null);
    set({ token: null, user: null, ready: true });
  },
  hydrate: () => {
    const stored = load();
    set({ token: stored?.token ?? null, user: stored?.user ?? null, ready: true });
  },
}));

export interface Toast {
  id: number;
  tone: "good" | "bad" | "info";
  text: string;
}

interface ToastState {
  toasts: Toast[];
  push: (tone: Toast["tone"], text: string) => void;
  dismiss: (id: number) => void;
}

let toastId = 0;

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (tone, text) => {
    toastId += 1;
    const id = toastId;
    set((state) => ({ toasts: [...state.toasts, { id, tone, text }] }));
    setTimeout(() => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })), 5000);
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
