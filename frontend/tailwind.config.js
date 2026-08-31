/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Neutral ramp bridged to the CSS design tokens so every existing
        // `text-slate-*` / `bg-slate-*` / `text-white` utility becomes
        // theme-aware. Dark values equal Tailwind's own slate scale (the app
        // looks identical in dark); light theme inverts the ramp.
        // `<alpha-value>` keeps `/10`, `/50` opacity modifiers working.
        slate: {
          50: 'rgb(var(--tw-slate-50) / <alpha-value>)',
          100: 'rgb(var(--tw-slate-100) / <alpha-value>)',
          200: 'rgb(var(--tw-slate-200) / <alpha-value>)',
          300: 'rgb(var(--tw-slate-300) / <alpha-value>)',
          400: 'rgb(var(--tw-slate-400) / <alpha-value>)',
          500: 'rgb(var(--tw-slate-500) / <alpha-value>)',
          600: 'rgb(var(--tw-slate-600) / <alpha-value>)',
          700: 'rgb(var(--tw-slate-700) / <alpha-value>)',
          800: 'rgb(var(--tw-slate-800) / <alpha-value>)',
          900: 'rgb(var(--tw-slate-900) / <alpha-value>)',
          950: 'rgb(var(--tw-slate-950) / <alpha-value>)',
        },
        white: 'rgb(var(--tw-white) / <alpha-value>)',
        glass: {
          50: 'rgba(255, 255, 255, 0.05)',
          100: 'rgba(255, 255, 255, 0.10)',
          200: 'rgba(255, 255, 255, 0.15)',
          300: 'rgba(255, 255, 255, 0.20)',
        },
        neo: {
          light: 'rgba(255, 255, 255, 0.07)',
          dark: 'rgba(0, 0, 0, 0.5)',
        },
      },
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(31, 38, 135, 0.37)',
        'glass-sm': '0 4px 16px 0 rgba(31, 38, 135, 0.2)',
        'glass-lg': '0 12px 48px 0 rgba(31, 38, 135, 0.45)',
        'neo-outset': '8px 8px 16px rgba(0, 0, 0, 0.4), -8px -8px 16px rgba(255, 255, 255, 0.05)',
        'neo-inset': 'inset 4px 4px 8px rgba(0, 0, 0, 0.3), inset -4px -4px 8px rgba(255, 255, 255, 0.04)',
        'neo-sm': '4px 4px 8px rgba(0, 0, 0, 0.35), -4px -4px 8px rgba(255, 255, 255, 0.04)',
        'neo-lg': '12px 12px 24px rgba(0, 0, 0, 0.5), -12px -12px 24px rgba(255, 255, 255, 0.06)',
        'skew-bevel': '2px 2px 4px rgba(0, 0, 0, 0.3), -1px -1px 2px rgba(255, 255, 255, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.15)',
        'skew-pressed': 'inset 2px 2px 4px rgba(0, 0, 0, 0.3), inset -1px -1px 2px rgba(255, 255, 255, 0.05)',
        'glow-indigo': '0 0 20px rgba(99, 102, 241, 0.3), 0 0 40px rgba(99, 102, 241, 0.1)',
        'glow-emerald': '0 0 20px rgba(16, 185, 129, 0.3), 0 0 40px rgba(16, 185, 129, 0.1)',
        'glow-rose': '0 0 20px rgba(244, 63, 94, 0.3), 0 0 40px rgba(244, 63, 94, 0.1)',
        'glow-amber': '0 0 20px rgba(245, 158, 11, 0.3), 0 0 40px rgba(245, 158, 11, 0.1)',
      },
      animation: {
        'glow-pulse': 'glow-pulse 3s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
        'shimmer': 'shimmer 2.5s ease-in-out infinite',
        'slide-up': 'slide-up 0.5s ease-out',
        'fade-in': 'fade-in 0.4s ease-out',
        'scale-in': 'scale-in 0.3s ease-out',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
