// Tailwind v4 moves the PostCSS integration into its own package, and handles
// vendor prefixing itself — autoprefixer is no longer part of the chain.
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
