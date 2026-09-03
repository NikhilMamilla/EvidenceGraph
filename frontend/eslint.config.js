import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { globalIgnores } from 'eslint/config'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // API responses cross an untyped boundary; `any` is a deliberate,
      // consistent choice at those seams. Keep the signal without failing lint.
      '@typescript-eslint/no-explicit-any': 'warn',
      // A couple of files co-locate a small helper with a component (e.g. the
      // shared ConfusionMatrix). Fine for this codebase; HMR still works.
      'react-refresh/only-export-components': 'warn',
    },
  },
])
