"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { create } from "zustand";

import { cx } from "./ui";

interface ThemeState {
  dark: boolean;
  ready: boolean;
  set: (dark: boolean) => void;
}

const useThemeStore = create<ThemeState>((set) => ({
  dark: false,
  ready: false,
  set: (dark) => set({ dark, ready: true }),
}));

function apply(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  try {
    window.localStorage.setItem("campusflow-theme", dark ? "dark" : "light");
  } catch {
    return;
  }
}

export function useTheme(): [boolean, () => void] {
  const { dark, ready, set } = useThemeStore();
  useEffect(() => {
    if (ready) return;
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem("campusflow-theme");
    } catch {
      stored = null;
    }
    set(stored ? stored === "dark" : true);
  }, [ready, set]);
  const toggle = () => {
    apply(!dark);
    set(!dark);
  };
  return [dark, toggle];
}

export function ThemeToggle({ className }: { className?: string }) {
  const [dark, toggle] = useTheme();
  return (
    <button
      onClick={toggle}
      role="switch"
      aria-checked={dark}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      className={cx("relative grid h-9 w-9 place-items-center overflow-hidden rounded-full border border-line bg-surface text-ink transition duration-200 hover:border-primary hover:bg-surface2 active:scale-90", className)}
    >
      <Sun className={cx("absolute h-[18px] w-[18px] transition duration-300", dark ? "-rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100")} aria-hidden />
      <Moon className={cx("absolute h-[18px] w-[18px] transition duration-300", dark ? "rotate-0 scale-100 opacity-100" : "rotate-90 scale-0 opacity-0")} aria-hidden />
    </button>
  );
}
