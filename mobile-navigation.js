document.addEventListener("DOMContentLoaded", () => {
  const footer = document.querySelector(".sidebar-footer");
  if (!footer || footer.querySelector(".mobile-reminders-link")) return;
  const reminderLink = document.createElement("a");
  reminderLink.className = "mobile-reminders-link";
  reminderLink.href = "/feature/reminders";
  reminderLink.innerHTML = '<span class="material-symbols-outlined">notifications_active</span>Medicine Reminders';
  const assistantLink = footer.querySelector('a[href="/feature/assistant"]');
  if (assistantLink) footer.insertBefore(reminderLink, assistantLink);
  else footer.prepend(reminderLink);
});
