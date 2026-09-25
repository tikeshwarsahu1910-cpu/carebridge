document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".top-header, .feature-nav");
  if (!header || document.querySelector(".mobile-menu-toggle")) return;

  const toggle = document.createElement("button");
  toggle.className = "mobile-menu-toggle";
  toggle.setAttribute("aria-label", "Open menu");
  toggle.innerHTML = '<span class="material-symbols-outlined">menu</span>';

  const backdrop = document.createElement("div");
  backdrop.className = "mobile-menu-backdrop";
  const drawer = document.createElement("aside");
  drawer.className = "mobile-drawer";
  drawer.innerHTML = `
    <div class="mobile-drawer-head"><b>CareBridge</b><button class="mobile-menu-close" aria-label="Close menu"><span class="material-symbols-outlined">close</span></button></div>
    <p class="mobile-drawer-subtitle">Post-Discharge Care</p>
    <nav>
      <a href="/"><span class="material-symbols-outlined">dashboard</span>Overview<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/care-plan"><span class="material-symbols-outlined">assignment</span>My Care Plan<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/medications"><span class="material-symbols-outlined">medication</span>Medications<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/reminders"><span class="material-symbols-outlined">notifications_active</span>Medicine Reminders<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/appointments"><span class="material-symbols-outlined">calendar_month</span>Appointments<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/care-circle"><span class="material-symbols-outlined">group</span>Care Circle<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/safety"><span class="material-symbols-outlined">health_and_safety</span>Safety Checks<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/assistant"><span class="material-symbols-outlined">smart_toy</span>Care Assistant<span class="material-symbols-outlined">chevron_right</span></a>
      <a href="/feature/help"><span class="material-symbols-outlined">help</span>Help &amp; Support<span class="material-symbols-outlined">chevron_right</span></a>
    </nav>
    <div class="mobile-drawer-controls"><button id="mobileLanguageToggle">हिन्दी</button><button id="mobileThemeToggle"><span class="material-symbols-outlined">dark_mode</span>Dark mode</button></div>`;

  document.body.append(backdrop, drawer);
  header.prepend(toggle);
  const setOpen = open => document.body.classList.toggle("mobile-drawer-open", open);
  toggle.onclick = () => setOpen(true);
  backdrop.onclick = () => setOpen(false);
  drawer.querySelector(".mobile-menu-close").onclick = () => setOpen(false);
  drawer.querySelectorAll("a").forEach(link => link.onclick = () => setOpen(false));

  const syncControls = () => {
    const hindi = localStorage.getItem("carebridgeLanguage") === "hi";
    const dark = document.body.classList.contains("dark-mode");
    drawer.querySelector("#mobileLanguageToggle").textContent = hindi ? "EN" : "हिन्दी";
    drawer.querySelector("#mobileThemeToggle").innerHTML = `<span class="material-symbols-outlined">${dark ? "light_mode" : "dark_mode"}</span>${dark ? "Light mode" : "Dark mode"}`;
  };
  drawer.querySelector("#mobileLanguageToggle").onclick = () => { document.querySelector("#languageToggle, #featureLanguage")?.click(); syncControls(); };
  drawer.querySelector("#mobileThemeToggle").onclick = () => { document.querySelector("#themeToggle, #featureTheme")?.click(); syncControls(); };
  syncControls();
});
