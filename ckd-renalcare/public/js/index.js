
(() => {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("rc-mobile-toggle");
    const nav = document.getElementById("rc-nav-links");

    const signin = document.getElementById("rc-signin");
    const signinTrigger = document.getElementById("rc-signin-trigger");
    const signinPopup = document.getElementById("rc-signin-popup");

    const video = document.getElementById("rc-hero-video");

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    );

    /* SIGN-IN POPUP */

    function openSigninPopup() {
      if (!signinPopup || !signinTrigger) return;

      signinPopup.hidden = false;
      signinTrigger.setAttribute("aria-expanded", "true");
    }

    function closeSigninPopup() {
      if (!signinPopup || !signinTrigger) return;

      signinPopup.hidden = true;
      signinTrigger.setAttribute("aria-expanded", "false");
    }

    function toggleSigninPopup() {
      if (!signinPopup) return;

      if (signinPopup.hidden) {
        openSigninPopup();
      } else {
        closeSigninPopup();
      }
    }

    if (signinTrigger && signinPopup) {
      signinTrigger.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleSigninPopup();
      });

      /*
       * Close when the user clicks anywhere outside the popup
       * and its Sign in button.
       */
      document.addEventListener("click", (event) => {
        if (signin && !signin.contains(event.target)) {
          closeSigninPopup();
        }
      });

      /*
       * Close the popup when the user presses Escape.
       */
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !signinPopup.hidden) {
          closeSigninPopup();
          signinTrigger.focus();
        }
      });

      /*
       * Close the popup after a role link is selected.
       */
      signinPopup.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
          closeSigninPopup();
        });
      });
    }

    /* MOBILE NAVIGATION */

    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const isOpen = nav.classList.toggle("is-open");

        toggle.setAttribute("aria-expanded", String(isOpen));
        toggle.textContent = isOpen ? "Close ✕" : "Menu ☰";

        if (!isOpen) {
          closeSigninPopup();
        }
      });

      /*
       * Close mobile navigation after choosing a section link.
       * Do not close it when clicking the Sign in trigger.
       */
      nav.querySelectorAll('a[href^="#"]').forEach((link) => {
        link.addEventListener("click", () => {
          nav.classList.remove("is-open");
          toggle.setAttribute("aria-expanded", "false");
          toggle.textContent = "Menu ☰";
          closeSigninPopup();
        });
      });

      /*
       * On larger screens, remove any stale mobile menu state.
       */
      window.addEventListener("resize", () => {
        if (window.innerWidth > 700) {
          nav.classList.remove("is-open");
          toggle.setAttribute("aria-expanded", "false");
          toggle.textContent = "Menu ☰";
        }
      });
    }

    /* BACKGROUND VIDEO */

    if (video) {
      if (reducedMotion.matches) {
        video.pause();
        video.removeAttribute("autoplay");
      } else {
        const playPromise = video.play();

        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(() => {
            /*
             * If autoplay is blocked or the video is unavailable,
             * the poster image remains as the background fallback.
             */
          });
        }
      }
    }

    /* SCROLL REVEAL ANIMATIONS */

    const revealItems = document.querySelectorAll(".rc-reveal");

    if (
      reducedMotion.matches ||
      !("IntersectionObserver" in window)
    ) {
      revealItems.forEach((item) => {
        item.classList.add("is-visible");
      });
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12 }
      );

      revealItems.forEach((item) => {
        observer.observe(item);
      });
    }
  });
})();
