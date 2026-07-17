module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: ['plugin:vue/vue3-essential'],
  parser: 'vue-eslint-parser',
  parserOptions: {
    ecmaVersion: 'latest',
    parser: '@typescript-eslint/parser',
    sourceType: 'module',
  },
  plugins: ['@typescript-eslint'],
  ignorePatterns: ['dist/', 'node_modules/', 'playwright-report/', 'test-results/'],
  rules: {
    'vue/multi-word-component-names': 'off',
  },
}
