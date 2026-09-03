import type { Config } from "tailwindcss";

/**
 * Palette follows the GOV.UK / NHS design-system conventions: black text on
 * white, one link blue, a yellow focus state, and a small set of reserved
 * status colours. Nothing here is decorative.
 */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0c0c",
        secondary: "#505a5f",
        border: "#b1b4b6",
        canvas: "#f3f2f1",
        link: "#1d70b8",
        "link-hover": "#003078",
        focus: "#ffdd00",
        brand: "#1d70b8",
        success: "#00703c",
        error: "#d4351c",
        warning: "#f47738",
      },
      fontFamily: {
        sans: ["Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      maxWidth: {
        page: "1100px",
      },
    },
  },
  plugins: [],
} satisfies Config;
