(() => {
  const soundIsEnabled = () => localStorage.getItem("carebridgeReminderSound") !== "off";

  async function playReminderSound() {
    if (!soundIsEnabled()) return;
    try {
      const audio = new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") await audio.resume();
      const now = audio.currentTime;
      [0, 0.22].forEach((delay, index) => {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = index ? 784 : 659;
        gain.gain.setValueAtTime(0.0001, now + delay);
        gain.gain.exponentialRampToValueAtTime(0.13, now + delay + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + 0.17);
        oscillator.connect(gain).connect(audio.destination);
        oscillator.start(now + delay);
        oscillator.stop(now + delay + 0.19);
      });
      setTimeout(() => audio.close(), 700);
    } catch (_) {
      status("Your browser blocked the sound. Click Test sound again.");
    }
  }

  function status(message) {
    const target = document.querySelector("#reminderStatus, #featureStatus");
    if (target) target.textContent = message;
  }

  window.toggleReminderSound = () => {
    const enabled = !soundIsEnabled();
    localStorage.setItem("carebridgeReminderSound", enabled ? "on" : "off");
    const button = document.querySelector(".sound-toggle-button");
    if (button) button.textContent = enabled ? "Sound: On" : "Sound: Off";
    if (enabled) playReminderSound();
    status(enabled ? "✓ CareBridge reminder sound is on." : "CareBridge reminder sound is off.");
  };

  window.enableReminders = () => {
    if (!("Notification" in window)) {
      status("Browser notifications are not supported on this device.");
      return;
    }
    Notification.requestPermission().then(permission => {
      if (permission !== "granted") {
        status("Enable notifications in Chrome and Windows settings, then try again.");
        return;
      }
      localStorage.setItem("carebridgeReminders", "on");
      playReminderSound();
      new Notification("CareBridge reminders enabled", { body: "You will receive medicine reminder alerts on this device." });
      status("✓ Reminders and CareBridge sound are enabled.");
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    const appointments = document.querySelector(".appointment-panel");
    const reminders = document.querySelector(".reminder-panel");
    if (appointments && !appointments.id) appointments.id = "appointments";
    if (reminders && !reminders.id) reminders.id = "reminders";

    const enableButton = [...document.querySelectorAll("button")].find(button => /enable reminders|^enable$/i.test(button.textContent.trim()));
    if (!enableButton || document.querySelector(".sound-toggle-button")) return;
    const soundButton = document.createElement("button");
    soundButton.type = "button";
    soundButton.className = "text-button sound-toggle-button";
    soundButton.textContent = soundIsEnabled() ? "Sound: On" : "Sound: Off";
    soundButton.addEventListener("click", window.toggleReminderSound);
    enableButton.insertAdjacentElement("afterend", soundButton);
  });
})();
