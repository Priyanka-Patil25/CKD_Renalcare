document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.parentElement.querySelector("input");
      if (!input) return;
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.textContent = visible ? "Hide" : "Show";
      button.setAttribute("aria-pressed", String(visible));
      input.focus();
    });
  });

  const form = document.querySelector("[data-login]");
  if (form && window.Api) {
    const role = form.dataset.login;
    const error = form.querySelector(".form-error");
    const submit = form.querySelector('[type="submit"]');
    const initialLabel = submit?.innerHTML || "";
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.textContent = "";
      error.classList.remove("error");
      if (!form.reportValidity()) return;
      const fields = new FormData(form);
      if (submit) {
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        submit.textContent = submit.dataset.loadingLabel || "Signing in…";
      }
      try {
        const result = await Api.login(String(fields.get("identity") || "").trim(), fields.get("password"));
        if (result.role !== role && result.role !== "admin") {
          sessionStorage.removeItem("rc_auth");
          throw new Error("This account is for the " + result.role + " workspace.");
        }
        location.href = role === "doctor" ? "/doctor.html" : "/reception.html";
      } catch (exception) {
        error.textContent = exception?.message || "Sign in failed. Please try again.";
        error.classList.add("error");
        if (submit) {
          submit.disabled = false;
          submit.removeAttribute("aria-busy");
          submit.innerHTML = initialLabel;
        }
      }
    });
  }

  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.documentElement.classList.add("js-reveal");
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12 });
    document.querySelectorAll(".reveal").forEach((element) => observer.observe(element));
  }
});
