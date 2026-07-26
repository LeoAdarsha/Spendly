// main.js — students will add JavaScript here as features are built

// Lucide swaps every <i data-lucide="..."> for an inline <svg>. Guarded so a
// blocked CDN leaves the page working instead of throwing.
document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) lucide.createIcons();
});
