document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-auto-submit]").forEach((element) => {
    element.addEventListener("change", () => element.form && element.form.submit());
  });
});
