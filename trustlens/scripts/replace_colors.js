// replace_colors.js
// Simple script to replace raw hex colors in static/app.css with CSS variables
const fs = require('fs');
const path = require('path');
const cssPath = path.join(__dirname, '..', 'static', 'app.css');
let css = fs.readFileSync(cssPath, 'utf8');
const replacements = [
  {hex: '#121212', var: '--bg-base'},
  {hex: '#181818', var: '--bg-surface-1'},
  {hex: '#1DB954', var: '--accent-spotify-green'},
  {hex: '#00F0FF', var: '--accent-cyan-forensics'},
  {hex: '#526b91', var: '--brand-mark-border'},
  {hex: '#1a2432', var: '--brand-mark-bg'},
  {hex: '#bad0f5', var: '--brand-mark-color'},
  {hex: '#a6c5ff', var: '--button-primary-bg'},
  {hex: '#c0d5ff', var: '--button-primary-hover-bg'},
  {hex: '#7da8ef', var: '--button-primary-border'}
];
replacements.forEach(r => {
  const regex = new RegExp(r.hex, 'gi');
  css = css.replace(regex, `var(${r.var})`);
});
fs.writeFileSync(cssPath, css, 'utf8');
console.log('Color replacement completed.');
