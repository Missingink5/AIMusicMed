"use client";

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setDark(document.documentElement.dataset.theme === "dark"));
    return () => cancelAnimationFrame(frame);
  }, []);
  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    localStorage.setItem("aim-theme", next ? "dark" : "light");
  }
  return <button className="icon-button" onClick={toggle} aria-label={dark ? "切换到浅色模式" : "切换到深色模式"}>{dark ? "☀" : "☾"}</button>;
}
