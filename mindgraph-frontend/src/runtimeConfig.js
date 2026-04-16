export const runtimeConfig =
  typeof window !== "undefined" && window.__RUNTIME_CONFIG__
    ? window.__RUNTIME_CONFIG__
    : {};

export const getRuntimeConfig = (key) =>
  runtimeConfig[key] || process.env[key] || "";
