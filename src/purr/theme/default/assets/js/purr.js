/**
 * Purr Default Theme — Minimal JS
 *
 * - Theme toggle (light/dark, persisted to localStorage)
 * - Scroll-to-top (appears after scrolling down)
 */

(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // Theme toggle
  // -----------------------------------------------------------------------

  var STORAGE_KEY = "purr-theme";

  function getPreferred() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }

  // Listen for toggle button clicks
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".theme-toggle");
    if (!btn) return;
    var current = document.documentElement.getAttribute("data-theme") || getPreferred();
    applyTheme(current === "dark" ? "light" : "dark");
  });

  // Respect system preference changes
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", function (e) {
      if (!localStorage.getItem(STORAGE_KEY)) {
        applyTheme(e.matches ? "dark" : "light");
      }
    });

  // -----------------------------------------------------------------------
  // Scroll-to-top
  // -----------------------------------------------------------------------

  var scrollBtn = null;

  function createScrollBtn() {
    scrollBtn = document.createElement("button");
    scrollBtn.className = "scroll-to-top";
    scrollBtn.setAttribute("aria-label", "Scroll to top");
    scrollBtn.innerHTML = "&#8593;"; // ↑
    scrollBtn.style.cssText =
      "position:fixed;bottom:1.5rem;right:1.5rem;width:2.5rem;height:2.5rem;" +
      "border-radius:50%;border:1px solid var(--purr-border);background:var(--purr-surface);" +
      "color:var(--purr-text-secondary);font-size:1.1rem;cursor:pointer;opacity:0;" +
      "transition:opacity 0.2s;z-index:50;display:flex;align-items:center;" +
      "justify-content:center;line-height:1";
    scrollBtn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    document.body.appendChild(scrollBtn);
  }

  function onScroll() {
    if (!scrollBtn) createScrollBtn();
    scrollBtn.style.opacity = window.scrollY > 300 ? "1" : "0";
    scrollBtn.style.pointerEvents = window.scrollY > 300 ? "auto" : "none";
  }

  var ticking = false;
  window.addEventListener(
    "scroll",
    function () {
      if (!ticking) {
        requestAnimationFrame(function () {
          onScroll();
          ticking = false;
        });
        ticking = true;
      }
    },
    { passive: true }
  );
})();
