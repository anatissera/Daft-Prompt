import { createRequire } from "module";

const require = createRequire(import.meta.url);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // tone's "module" field (its ESM build) has circular-import binding issues
    // that break under Webpack, surfacing as "Tone.X is not a constructor" in
    // @magenta/music. Force resolution to tone's UMD bundle instead.
    config.resolve.alias.tone = require.resolve("tone/build/Tone.js", {
      paths: [require.resolve("@magenta/music/package.json")],
    });
    return config;
  },
};

export default nextConfig;
