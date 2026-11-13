/* Applies the saved/OS theme before first paint (external file: CSP forbids inline scripts). */
try { var t = localStorage.getItem("coldguard-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); document.documentElement.dataset.theme = t } catch (e) { /* storage blocked */ }
