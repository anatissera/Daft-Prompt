import { createRequire } from "module";

const require = createRequire(import.meta.url);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // Tone's ESM build has circular-import binding issues under Webpack. Resolve
    // its local UMD bundle directly; playback has no Magenta dependency.
    config.resolve.alias.tone = require.resolve("tone/build/Tone.js");
    return config;
  },
};

export default nextConfig;
