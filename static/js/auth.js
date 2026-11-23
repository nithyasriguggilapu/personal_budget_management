document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-toggle-password]");
  if (!button) return;

  const input = document.getElementById(button.dataset.togglePassword);
  if (!input) return;

  const visible = input.type === "password";
  input.type = visible ? "text" : "password";
  button.textContent = visible ? "Hide" : "Show";
  button.setAttribute("aria-label", `${visible ? "Hide" : "Show"} password`);
  button.setAttribute("aria-pressed", String(visible));
});
