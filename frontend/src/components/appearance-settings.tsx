"use client";

import { Laptop, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import {
  readThemePreference,
  saveThemePreference,
  type ThemePreference,
} from "@/lib/theme";

const OPTIONS: Array<{
  value: ThemePreference;
  label: string;
  icon: typeof Sun;
}> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Laptop },
];

export function AppearanceSettings() {
  const [value, setValue] = useState<ThemePreference>("system");
  useEffect(() => setValue(readThemePreference()), []);

  return (
    <section
      id="appearance"
      aria-labelledby="appearance-heading"
      className="rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-5 sm:p-6"
    >
      <h2 id="appearance-heading" className="text-base font-semibold">
        Appearance
      </h2>
      <p className="mt-1 text-sm text-[color:var(--silver)]">
        Choose a theme or follow your operating system automatically.
      </p>
      <fieldset className="mt-5 grid grid-cols-3 gap-2 rounded-xl bg-[color:var(--void)]/60 p-1.5">
        <legend className="sr-only">Color theme</legend>
        {OPTIONS.map(({ value: option, label, icon: Icon }) => (
          <label
            key={option}
            className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition ${value === option ? "bg-[color:var(--near-white)] text-[color:var(--void)] shadow-sm" : "text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)]"}`}
          >
            <input
              className="sr-only"
              type="radio"
              name="theme"
              value={option}
              checked={value === option}
              onChange={() => {
                setValue(option);
                saveThemePreference(option);
              }}
            />
            <Icon aria-hidden="true" className="h-4 w-4" />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
    </section>
  );
}
