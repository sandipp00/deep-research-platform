import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/store/theme";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useTheme((s) => s.theme);
  const toggle = useTheme((s) => s.toggle);

  return (
    <button
      onClick={toggle}
      aria-label="Toggle color theme"
      className={`grid place-items-center w-10 h-10 rounded-xl border transition
        border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50
        dark:border-white/[0.08] dark:bg-white/[0.04] dark:text-zinc-300 dark:hover:bg-white/[0.08]
        ${className}`}
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
