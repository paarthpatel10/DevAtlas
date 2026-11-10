import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // The repo root has its own package-lock.json (Neon tooling); pin the app root here.
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
