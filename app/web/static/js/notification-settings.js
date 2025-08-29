/**
 * Notification Settings Manager
 * Handles user preferences for notifications
 */
class NotificationSettings {
  constructor() {
    console.log("NotificationSettings: Initializing...");
    this.csrfToken = document
      .querySelector('meta[name="csrf-token"]')
      .getAttribute("content");
    this.settings = {};
    this.registration = null;

    // Get all UI elements
    this.blogConnectionStatus = document.getElementById("blogConnectionStatus");
    this.requestPermissionBtn = document.getElementById("requestPermissionBtn");
    this.toggleNotificationsBtn = document.getElementById(
      "toggleNotificationsBtn",
    );
    this.testNotificationBtn = document.getElementById("testNotificationBtn");
    this.keywordFilterEnabled = document.getElementById("keywordFilterEnabled");
    this.keywordFilterOptions = document.getElementById("keywordFilterOptions");
    this.locationFilterEnabled = document.getElementById(
      "locationFilterEnabled",
    );
    this.locationFilterOptions = document.getElementById(
      "locationFilterOptions",
    );
    this.keywordInput = document.getElementById("keywordInput");
    this.addKeywordBtn = document.getElementById("addKeywordBtn");
    this.keywordSearch = document.getElementById("keywordSearch");
    this.keywordsContainer = document.getElementById("keywordsContainer");
    this.selectAllKeywords = document.getElementById("selectAllKeywords");
    this.deselectAllKeywords = document.getElementById("deselectAllKeywords");
    this.localeMenuButton = document.getElementById("locale-menu-button");
    this.localeMenuDropdown = document.getElementById("locale-menu-dropdown");
    this.currentLocaleLabel = document.getElementById("current-locale-label");

    const optionElements = document.querySelectorAll("#keywordOptions option");
    this.availableKeywords = Array.from(optionElements).map((o) => o.value);

    // Validate UI elements
    this.validateUIElements();

    // Initialize immediately
    this.initialize();
  }

  validateUIElements() {
    const requiredElements = [
      "blogConnectionStatus",
      "requestPermissionBtn",
      "toggleNotificationsBtn",
      "testNotificationBtn",
      "keywordFilterEnabled",
      "keywordFilterOptions",
      "locationFilterEnabled",
      "locationFilterOptions",
      "keywordInput",
      "addKeywordBtn",
      "keywordSearch",
      "keywordsContainer",
      "selectAllKeywords",
      "deselectAllKeywords",
      "localeMenuButton",
      "localeMenuDropdown",
      "currentLocaleLabel",
    ];

    const missingElements = requiredElements.filter((name) => !this[name]);
    if (missingElements.length > 0) {
      console.error("Missing required UI elements:", missingElements);
      throw new Error("Required UI elements not found");
    }
  }

  async initialize() {
    try {
      // Load settings from server
      await this.loadSettings();
      this.updateKeywordsUI();

      // Verify push subscription status
      await this.checkPushStatus();

      // Initialize event listeners
      this.initializeEventListeners();

      // Set up service worker update handling
      this.setupServiceWorkerUpdateHandling();

      // Set initial permission button state
      if ("Notification" in window) {
        this.updatePermissionButton(Notification.permission);
      } else {
        this.updatePermissionButton("denied");
      }
    } catch (error) {
      console.error("Error during initialization:", error);
      this.showError("Failed to initialize notification settings");
    }
  }

  setupServiceWorkerUpdateHandling() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        console.log("New service worker activated");
        this.checkServiceWorkerRegistration();
      });

      navigator.serviceWorker.addEventListener("message", (event) => {
        if (event.data && event.data.type === "SKIP_WAITING") {
          console.log("New service worker waiting, activating...");
          this.registration.waiting.postMessage({ type: "SKIP_WAITING" });
        }
      });
    }
  }

  async checkServiceWorkerRegistration() {
    if (!this.registrationStatus) return;

    if (!("serviceWorker" in navigator)) {
      this.updateRegistrationStatus(
        "not-supported",
        "Service Worker not supported",
      );
      return;
    }

    try {
      // Unregister any old service workers first
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        if (
          registration.active &&
          registration.active.scriptURL.includes("service-worker.js")
        ) {
          await registration.unregister();
          console.log("Unregistered old service worker");
        }
      }

      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) {
        console.log("Service Worker already registered:", registration);
        this.registration = registration;
        this.updateRegistrationStatus("registered");

        // Check for updates
        await registration.update();
      } else {
        console.log("No Service Worker registration found");
        this.updateRegistrationStatus("not-registered");
        // Try to register if not found
        await this.registerServiceWorker();
      }
    } catch (error) {
      console.error("Error checking Service Worker registration:", error);
      this.updateRegistrationStatus("error", error.message);
      throw error;
    }
  }

  async loadSettings() {
    try {
      const response = await fetch("/api/notifications/settings", {
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": this.csrfToken,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load settings: ${response.status}`);
      }

      const settings = await response.json();

      // Validate settings
      if (!this.validateSettings(settings)) {
        throw new Error("Invalid settings received from server");
      }

      this.settings = settings;
      console.log(
        "NotificationSettings: Loaded settings from server:",
        this.settings,
      );

      // Update UI based on loaded settings
      if (this.currentLocaleLabel) {
        const lang = this.settings.language || "en";
        this.currentLocaleLabel.textContent = lang.toUpperCase();
        this.formatDates(lang);
      }
      this.updateToggleButton(
        this.settings.desktopNotifications || this.settings.pushNotifications,
      );
      this.updateKeywordFilterButton(this.settings.keywordFilter.enabled);
      this.updateLocationFilterButton(this.settings.locationFilter.enabled);
      this.updateKeywordsUI();
      this.updateLocationsUI();
    } catch (error) {
      console.error("Error loading settings:", error);
      // Fallback to default settings
      const defaultSettings = {
        language: "en",
        desktopNotifications: true,
        pushNotifications: true,
        keywordFilter: {
          enabled: false,
        },
        locationFilter: {
          enabled: false,
          locations: [],
        },
        keywords: [],
      };
      this.settings = defaultSettings;
      this.showError("Failed to load settings, using defaults");
    }
  }

  validateSettings(settings) {
    const requiredFields = [
      "language",
      "desktopNotifications",
      "pushNotifications",
      "keywordFilter",
      "locationFilter",
      "keywords",
    ];

    // Check required fields
    if (!requiredFields.every((field) => field in settings)) {
      console.error("Missing required settings fields");
      return false;
    }

    // Validate types
    if (
      typeof settings.language !== "string" ||
      typeof settings.desktopNotifications !== "boolean" ||
      typeof settings.pushNotifications !== "boolean" ||
      !Array.isArray(settings.keywords)
    ) {
      console.error("Invalid boolean settings");
      return false;
    }

    // Validate location filter
    if (
      !settings.locationFilter ||
      typeof settings.locationFilter.enabled !== "boolean" ||
      !Array.isArray(settings.locationFilter.locations)
    ) {
      console.error("Invalid location filter settings");
      return false;
    }

    // Validate keyword filter
    if (
      !settings.keywordFilter ||
      typeof settings.keywordFilter.enabled !== "boolean"
    ) {
      console.error("Invalid keyword filter settings");
      return false;
    }

    if (!["en", "hu", "sv"].includes(settings.language)) {
      console.error("Invalid language setting");
      return false;
    }

    return true;
  }

  async saveSettings() {
    try {
      // Validate settings before saving
      if (!this.validateSettings(this.settings)) {
        throw new Error("Invalid settings");
      }

      const response = await fetch("/api/notifications/settings", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken": this.csrfToken,
        },
        body: JSON.stringify(this.settings),
      });

      if (!response.ok) {
        throw new Error(`Failed to save settings: ${response.status}`);
      }

      console.log("NotificationSettings: Settings saved successfully");
    } catch (error) {
      console.error("Error saving settings:", error);
      this.showError("Failed to save settings");
      throw error;
    }
  }

  async requestPermission() {
    if (!("Notification" in window)) {
      console.error("Notifications not supported");
      return "denied";
    }

    try {
      // First check current permission
      const currentPermission = Notification.permission;
      if (currentPermission === "granted") {
        console.log("Notifications already granted");
        return "granted";
      }
      if (currentPermission === "denied") {
        console.log("Notifications already denied");
        return "denied";
      }

      // Request permission
      console.log("Requesting notification permission...");
      const permission = await Notification.requestPermission();
      console.log("Permission result:", permission);

      this.updatePermissionStatus(permission);

      if (permission === "granted") {
        if (this.requestPermissionBtn) {
          this.requestPermissionBtn.classList.add("hidden");
        }
        // Show a test notification
        new Notification("Notifications Enabled", {
          body: "You will now receive notifications for new posts.",
          icon: "/static/img/notification/icon.png",
        });
        this.checkRegistrationStatus();
      }
      return permission;
    } catch (error) {
      console.error("Error requesting permission:", error);
      this.updatePermissionStatus("error", "Error requesting permission");
      return "denied";
    }
  }

  async registerServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      console.log("Service Worker not supported");
      this.updateRegistrationStatus(
        "not-supported",
        "Service Worker not supported",
      );
      return;
    }

    try {
      console.log("Registering Service Worker...");
      const registration = await navigator.serviceWorker.register(
        "/static/js/service-worker.js",
      );
      console.log("Service Worker registered:", registration);
      this.updateRegistrationStatus("registered");
    } catch (error) {
      console.error("Service Worker registration failed:", error);
      this.updateRegistrationStatus("error", "Registration failed");
    }
  }

  async checkRegistrationStatus() {
    if (!this.registrationStatus) return;

    try {
      if ("serviceWorker" in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        if (registration) {
          this.updateRegistrationStatus("registered");
        } else {
          // If not registered, try to register
          await this.registerServiceWorker();
        }
      } else {
        this.updateRegistrationStatus(
          "not-supported",
          "Service Worker not supported",
        );
      }
    } catch (error) {
      console.error("Error checking registration status:", error);
      this.updateRegistrationStatus("error", "Error checking status");
    }
  }

  updateRegistrationStatus(status, customMessage = null) {
    if (!this.registrationStatus) return;

    const statusMap = {
      registered: {
        text: "Registered",
        icon: "fa-check-circle",
        color: "text-green-600",
      },
      "not-registered": {
        text: "Not registered",
        icon: "fa-times-circle",
        color: "text-red-600",
      },
      "not-supported": {
        text: customMessage || "Not supported",
        icon: "fa-times-circle",
        color: "text-red-600",
      },
      error: {
        text: customMessage || "Error",
        icon: "fa-exclamation-circle",
        color: "text-red-600",
      },
    };

    const statusInfo = statusMap[status] || statusMap["error"];
    this.registrationStatus.innerHTML = `
            <i class="fas ${statusInfo.icon} ${statusInfo.color}"></i>
            ${statusInfo.text}
        `;
  }

  initializeEventListeners() {
    // Request permission button
    if (this.requestPermissionBtn) {
      this.requestPermissionBtn.addEventListener("click", async () => {
        console.log("Request permission button clicked");
        await this.requestPermission();
      });
    }

    // Locale menu
    if (this.localeMenuButton && this.localeMenuDropdown) {
      const close = () => this.localeMenuDropdown.classList.add("hidden");
      this.localeMenuButton.addEventListener("click", (e) => {
        e.stopPropagation();
        this.localeMenuDropdown.classList.toggle("hidden");
      });
      document.addEventListener("click", (e) => {
        if (
          !this.localeMenuButton.contains(e.target) &&
          !this.localeMenuDropdown.contains(e.target)
        ) {
          close();
        }
      });
      this.localeMenuDropdown
        .querySelectorAll("a[data-locale]")
        .forEach((a) => {
          a.addEventListener("click", (e) => {
            e.preventDefault();
            const locale = a.dataset.locale;
            this.settings.language = locale;
            if (this.currentLocaleLabel) {
              this.currentLocaleLabel.textContent = locale.toUpperCase();
            }
            this.formatDates(locale);
            this.saveSettings();
            close();
          });
        });
    }

    // Toggle notifications button
    if (this.toggleNotificationsBtn) {
      this.toggleNotificationsBtn.addEventListener("click", async () => {
        const isEnabled =
          this.settings.desktopNotifications || this.settings.pushNotifications;
        if (isEnabled) {
          // Disable notifications
          this.settings.desktopNotifications = false;
          this.settings.pushNotifications = false;

          // Unsubscribe from push notifications and unregister service worker
          if (typeof window.unsubscribeFromPush === "function") {
            await window.unsubscribeFromPush();
          } else {
            console.warn("unsubscribeFromPush function not available");
          }
        } else {
          // Enable notifications
          this.settings.desktopNotifications = true;
          this.settings.pushNotifications = true;
          if (Notification.permission !== "granted") {
            await this.requestPermission();
          }

          // Re-subscribe to push notifications
          if (typeof window.subscribeForPush === "function") {
            await window.subscribeForPush();
          } else {
            console.warn("subscribeForPush function not available");
          }
        }
        this.saveSettings();
        this.updateToggleButton(!isEnabled);

        // Immediately update test notification button state
        if (this.testNotificationBtn) {
          const newEnabled =
            this.settings.desktopNotifications ||
            this.settings.pushNotifications;
          this.testNotificationBtn.disabled = !newEnabled;
        }
      });
    }

    // Test notification button
    if (this.testNotificationBtn) {
      this.testNotificationBtn.addEventListener("click", async () => {
        const isEnabled =
          this.settings.desktopNotifications || this.settings.pushNotifications;
        if (!isEnabled) {
          console.log(
            "Cannot show test notification - notifications are disabled",
          );
          return;
        }

        // Show an immediate local notification for real-time feedback
        try {
          if (
            "Notification" in window &&
            Notification.permission === "granted" &&
            this.settings.desktopNotifications
          ) {
            const n = new Notification("🧪 Test Notification", {
              body: "This is a test notification to verify your settings are working correctly.",
              icon: "/static/img/notification/icon.png",
              tag: "test-notification",
              requireInteraction: false,
            });
            setTimeout(() => {
              try {
                n.close();
              } catch (_) {}
            }, 8000);
          }
        } catch (e) {
          console.warn("Unable to show immediate test notification:", e);
        }

        // Also trigger server-side push test to verify push path
        try {
          const response = await fetch("/api/test-notification", {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": this.csrfToken,
            },
          });

          if (!response.ok) {
            throw new Error(
              `Failed to trigger notification: ${response.status}`,
            );
          }
          console.log("Test push notification triggered");
        } catch (error) {
          console.error("Error sending test notification:", error);
          this.showError("Failed to send test notification");
        }
      });
    }

    // Location filter toggle
    if (this.locationFilterEnabled) {
      this.locationFilterEnabled.addEventListener("click", () => {
        const newEnabled = !this.settings.locationFilter.enabled;

        // Check if enabling with no locations selected
        if (newEnabled && this.settings.locationFilter.locations.length === 0) {
          // Updated warning message - empty filters mean "no filter"
          console.warn(
            "Location filter enabled with no locations selected. Leaving filters blank will deliver all notifications.",
          );
          this.showWarning(
            "Location filter enabled with no locations selected. Leaving filters blank will deliver all notifications.",
          );
        }

        this.settings.locationFilter.enabled = newEnabled;
        this.updateLocationFilterButton(newEnabled);
        this.updateLocationsUI();
        this.saveSettings();
      });
    }

    // Keyword filter toggle
    if (this.keywordFilterEnabled) {
      this.keywordFilterEnabled.addEventListener("click", () => {
        const newEnabled = !this.settings.keywordFilter.enabled;

        // Check if enabling with no keywords selected
        if (newEnabled && this.settings.keywords.length === 0) {
          // Updated warning message - empty filters mean "no filter"
          console.warn(
            "Keyword filter enabled with no keywords selected. Leaving filters blank will deliver all notifications.",
          );
          this.showWarning(
            "Keyword filter enabled with no keywords selected. Leaving filters blank will deliver all notifications.",
          );
        }

        this.settings.keywordFilter.enabled = newEnabled;
        this.updateKeywordFilterButton(newEnabled);
        this.saveSettings();
      });
    }

    // Location search
    const locationSearch = document.getElementById("locationSearch");
    if (locationSearch) {
      locationSearch.addEventListener("input", (event) => {
        const searchTerm = event.target.value.toLowerCase();
        const locationItems =
          this.locationFilterOptions.querySelectorAll('[name="locations"]');

        locationItems.forEach((item) => {
          const label = item.nextElementSibling;
          const location = label.textContent.toLowerCase();
          const parent = item.closest("div");

          if (location.includes(searchTerm)) {
            parent.style.display = "";
          } else {
            parent.style.display = "none";
          }
        });
      });
    }

    // Select All Locations
    const selectAllBtn = document.getElementById("selectAllLocations");
    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", () => {
        const checkboxes =
          this.locationFilterOptions.querySelectorAll('[name="locations"]');
        checkboxes.forEach((checkbox) => {
          if (!checkbox.checked) {
            checkbox.checked = true;
            const location = checkbox.value;
            if (!this.settings.locationFilter.locations.includes(location)) {
              this.settings.locationFilter.locations.push(location);
            }
          }
        });
        this.saveSettings();
      });
    }

    // Deselect All Locations
    const deselectAllBtn = document.getElementById("deselectAllLocations");
    if (deselectAllBtn) {
      deselectAllBtn.addEventListener("click", () => {
        const checkboxes =
          this.locationFilterOptions.querySelectorAll('[name="locations"]');
        checkboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        this.settings.locationFilter.locations = [];

        // Warn if location filter is still enabled
        if (this.settings.locationFilter.enabled) {
          this.showWarning(
            "Location filter is enabled but no locations are selected. Leaving filters blank will deliver all notifications.",
          );
        }

        this.saveSettings();
      });
    }

    if (this.addKeywordBtn && this.keywordInput) {
      this.addKeywordBtn.addEventListener("click", () => {
        const kw = this.keywordInput.value.trim();
        if (kw.length < 3 || this.settings.keywords.length >= 20) return;
        if (!this.settings.keywords.includes(kw)) {
          this.settings.keywords.push(kw);
          if (!this.availableKeywords.includes(kw)) {
            this.availableKeywords.push(kw);
            const opt = document.createElement("option");
            opt.value = kw;
            document.getElementById("keywordOptions").appendChild(opt);
          }
          this.keywordInput.value = "";
          this.saveSettings();
          this.updateKeywordsUI();
        }
      });
    }

    if (this.keywordSearch) {
      this.keywordSearch.addEventListener("input", (event) => {
        const term = event.target.value.toLowerCase();
        const items =
          this.keywordsContainer.querySelectorAll('[name="keywords"]');
        items.forEach((item) => {
          const label = item.nextElementSibling;
          const txt = label.textContent.toLowerCase();
          const parent = item.closest("div");
          parent.style.display = txt.includes(term) ? "" : "none";
        });
      });
    }

    if (this.selectAllKeywords) {
      this.selectAllKeywords.addEventListener("click", () => {
        const boxes =
          this.keywordsContainer.querySelectorAll('[name="keywords"]');
        boxes.forEach((cb) => {
          if (!cb.checked) {
            cb.checked = true;
            if (!this.settings.keywords.includes(cb.value)) {
              this.settings.keywords.push(cb.value);
            }
          }
        });
        this.saveSettings();
      });
    }

    if (this.deselectAllKeywords) {
      this.deselectAllKeywords.addEventListener("click", () => {
        const boxes =
          this.keywordsContainer.querySelectorAll('[name="keywords"]');
        boxes.forEach((cb) => (cb.checked = false));
        this.settings.keywords = [];

        // Warn if keyword filter is still enabled
        if (this.settings.keywordFilter.enabled) {
          this.showWarning(
            "Keyword filter is enabled but no keywords are selected. Leaving filters blank will deliver all notifications.",
          );
        }

        this.saveSettings();
      });
    }

    if (this.keywordsContainer) {
      this.keywordsContainer.addEventListener("change", (event) => {
        if (event.target.type === "checkbox") {
          const kw = event.target.value;
          const checked = event.target.checked;
          if (checked) {
            if (!this.settings.keywords.includes(kw)) {
              this.settings.keywords.push(kw);
            }
          } else {
            this.settings.keywords = this.settings.keywords.filter(
              (k) => k !== kw,
            );

            // Warn if this was the last keyword and filter is still enabled
            if (
              this.settings.keywords.length === 0 &&
              this.settings.keywordFilter.enabled
            ) {
              this.showWarning(
                "Keyword filter is enabled but no keywords are selected. Leaving filters blank will deliver all notifications.",
              );
            }
          }
          this.saveSettings();
        }
      });
    }

    // Location checkboxes
    if (this.locationFilterOptions) {
      this.locationFilterOptions.addEventListener("change", (event) => {
        if (event.target.type === "checkbox") {
          const location = event.target.value;
          const checked = event.target.checked;
          if (checked) {
            if (!this.settings.locationFilter.locations.includes(location)) {
              this.settings.locationFilter.locations.push(location);
            }
          } else {
            this.settings.locationFilter.locations =
              this.settings.locationFilter.locations.filter(
                (l) => l !== location,
              );

            // Warn if this was the last location and filter is still enabled
            if (
              this.settings.locationFilter.locations.length === 0 &&
              this.settings.locationFilter.enabled
            ) {
              this.showWarning(
                "Location filter is enabled but no locations are selected. Leaving filters blank will deliver all notifications.",
              );
            }
          }
          this.saveSettings();
        }
      });
    }
  }

  updateUI() {
    // Update all button states

    // Update toggle button state
    if (this.toggleNotificationsBtn) {
      const isEnabled =
        this.settings.desktopNotifications || this.settings.pushNotifications;
      this.updateToggleButton(isEnabled);
    }

    if (this.currentLocaleLabel) {
      const lang = this.settings.language || "en";
      this.currentLocaleLabel.textContent = lang.toUpperCase();
      this.formatDates(lang);
    }

    // Update test notification button state
    if (this.testNotificationBtn) {
      const isEnabled =
        this.settings.desktopNotifications || this.settings.pushNotifications;
      this.testNotificationBtn.disabled = !isEnabled;

      // Create or update icon
      let icon = this.testNotificationBtn.querySelector("i");
      if (!icon) {
        icon = document.createElement("i");
        this.testNotificationBtn.prepend(icon);
      }

      if (isEnabled) {
        this.testNotificationBtn.className =
          "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors";
        icon.className = "fas fa-paper-plane mr-1";
        this.testNotificationBtn.textContent = "Send Notification";
        this.testNotificationBtn.prepend(icon);
      } else {
        this.testNotificationBtn.className =
          "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors";
        icon.className = "fas fa-paper-plane mr-1";
        this.testNotificationBtn.textContent = "Send Notification";
        this.testNotificationBtn.prepend(icon);
      }
    }
  }

  getSettings() {
    return { ...this.settings };
  }

  async checkPushStatus() {
    try {
      const resp = await fetch("/api/notifications/status", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && data.push_enabled === false) {
        this.settings.desktopNotifications = false;
        this.settings.pushNotifications = false;
        this.updateToggleButton(false);
        this.showError(
          "Push notifications are inactive. Please enable them again.",
        );
      }
    } catch (err) {
      console.warn("Failed to check push subscription status:", err);
    }
  }

  updatePermissionStatus(status, customMessage = null) {
    if (!this.permissionStatus) return;

    const statusMap = {
      granted: {
        text: "Granted",
        icon: "fa-check-circle",
        color: "text-green-600",
      },
      denied: {
        text: "Denied",
        icon: "fa-times-circle",
        color: "text-red-600",
      },
      default: {
        text: "Not requested",
        icon: "fa-question-circle",
        color: "text-yellow-600",
      },
      "not-supported": {
        text: customMessage || "Not supported",
        icon: "fa-times-circle",
        color: "text-red-600",
      },
    };

    const statusInfo = statusMap[status] || statusMap["not-supported"];
    this.permissionStatus.innerHTML = `
            <i class="fas ${statusInfo.icon} ${statusInfo.color}"></i>
            ${statusInfo.text}
        `;
  }

  updateToggleButton(isEnabled) {
    if (!this.toggleNotificationsBtn) return;

    // Create or update icon
    let icon = this.toggleNotificationsBtn.querySelector("i");
    if (!icon) {
      icon = document.createElement("i");
      this.toggleNotificationsBtn.prepend(icon);
    }

    if (isEnabled) {
      this.toggleNotificationsBtn.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-check mr-1";
      this.toggleNotificationsBtn.textContent = "Enabled";
      this.toggleNotificationsBtn.prepend(icon);
    } else {
      this.toggleNotificationsBtn.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-times mr-1";
      this.toggleNotificationsBtn.textContent = "Disabled";
      this.toggleNotificationsBtn.prepend(icon);
    }
  }

  updateLocationFilterButton(isEnabled) {
    if (!this.locationFilterEnabled) return;

    // Create or update icon
    let icon = this.locationFilterEnabled.querySelector("i");
    if (!icon) {
      icon = document.createElement("i");
      this.locationFilterEnabled.prepend(icon);
    }

    if (isEnabled) {
      this.locationFilterEnabled.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-check mr-1";
      this.locationFilterEnabled.textContent = "Enabled";
      this.locationFilterEnabled.prepend(icon);
      this.locationFilterOptions.classList.remove("hidden");
    } else {
      this.locationFilterEnabled.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-times mr-1";
      this.locationFilterEnabled.textContent = "Disabled";
      this.locationFilterEnabled.prepend(icon);
      this.locationFilterOptions.classList.add("hidden");
    }
  }

  updateKeywordFilterButton(isEnabled) {
    if (!this.keywordFilterEnabled) return;

    let icon = this.keywordFilterEnabled.querySelector("i");
    if (!icon) {
      icon = document.createElement("i");
      this.keywordFilterEnabled.prepend(icon);
    }

    if (isEnabled) {
      this.keywordFilterEnabled.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-check mr-1";
      this.keywordFilterEnabled.textContent = "Enabled";
      this.keywordFilterEnabled.prepend(icon);
      this.keywordFilterOptions.classList.remove("hidden");
    } else {
      this.keywordFilterEnabled.className =
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors";
      icon.className = "fas fa-times mr-1";
      this.keywordFilterEnabled.textContent = "Disabled";
      this.keywordFilterEnabled.prepend(icon);
      this.keywordFilterOptions.classList.add("hidden");
    }
  }

  updateKeywordsUI() {
    if (!this.keywordsContainer) return;
    const all = Array.from(
      new Set([...this.availableKeywords, ...this.settings.keywords]),
    ).sort();
    this.keywordsContainer.innerHTML = "";
    all.forEach((kw, idx) => {
      const wrapper = document.createElement("div");
      wrapper.className = "px-3 py-2 flex items-center gap-2";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = "keywords";
      cb.id = `kw-${idx}`;
      cb.value = kw;
      cb.className = "form-checkbox";
      cb.checked = this.settings.keywords.includes(kw);
      const label = document.createElement("label");
      label.setAttribute("for", `kw-${idx}`);
      label.className = "text-sm text-gray-700";
      label.textContent = kw;
      wrapper.appendChild(cb);
      wrapper.appendChild(label);
      this.keywordsContainer.appendChild(wrapper);
    });
  }

  updateLocationsUI() {
    if (!this.locationFilterOptions) return;
    const selected = this.settings.locationFilter.locations || [];
    const checkboxes =
      this.locationFilterOptions.querySelectorAll('[name="locations"]');
    checkboxes.forEach((cb) => {
      cb.checked = selected.includes(cb.value);
    });
  }

  updatePermissionButton(permission) {
    if (!this.requestPermissionBtn) return;

    const permissionGranted = document.getElementById("permissionGranted");
    if (!permissionGranted) return;

    // Create or update icon for request permission button
    let icon = this.requestPermissionBtn.querySelector("i");
    if (!icon) {
      icon = document.createElement("i");
      this.requestPermissionBtn.prepend(icon);
    }

    switch (permission) {
      case "granted":
        this.requestPermissionBtn.classList.add("hidden");
        permissionGranted.className =
          "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800";
        permissionGranted.classList.remove("hidden");
        break;
      case "denied":
        this.requestPermissionBtn.classList.remove("hidden");
        permissionGranted.classList.add("hidden");
        this.requestPermissionBtn.className =
          "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors";
        icon.className = "fas fa-times mr-1";
        this.requestPermissionBtn.textContent = "Disabled";
        this.requestPermissionBtn.prepend(icon);
        break;
      default:
        this.requestPermissionBtn.classList.remove("hidden");
        permissionGranted.classList.add("hidden");
        this.requestPermissionBtn.className =
          "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 hover:bg-yellow-200 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:ring-offset-2 transition-colors";
        icon.className = "fas fa-exclamation-triangle mr-1";
        this.requestPermissionBtn.textContent = "Click to Enable";
        this.requestPermissionBtn.prepend(icon);
    }
  }

  formatDates(locale) {
    document.querySelectorAll(".datetime").forEach((el) => {
      const iso = el.dataset.datetime;
      if (!iso) return;
      const d = new Date(iso);
      if (isNaN(d)) return;
      el.textContent = new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(d);
    });
  }

  showWarning(message) {
    // Create warning toast if it doesn't exist
    let toast = document.getElementById("warning-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "warning-toast";
      toast.className =
        "fixed bottom-4 right-4 bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded max-w-sm z-50";
      document.body.appendChild(toast);
    }

    // Show warning message
    toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                <span>${message}</span>
            </div>
        `;
    toast.style.display = "block";

    // Hide after 8 seconds
    setTimeout(() => {
      toast.style.display = "none";
    }, 8000);
  }

  showError(message) {
    // Create error toast if it doesn't exist
    let toast = document.getElementById("error-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "error-toast";
      toast.className =
        "fixed bottom-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded max-w-sm z-50";
      document.body.appendChild(toast);
    }

    // Show error message
    toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-times-circle mr-2"></i>
                <span>${message}</span>
            </div>
        `;
    toast.style.display = "block";

    // Hide after 5 seconds
    setTimeout(() => {
      toast.style.display = "none";
    }, 5000);
  }
}

// Initialize notification settings when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    console.log("NotificationSettings: DOM loaded, initializing...");
    window.notificationSettings = new NotificationSettings();
  });
} else {
  console.log(
    "NotificationSettings: DOM already loaded, initializing immediately...",
  );
  window.notificationSettings = new NotificationSettings();
}
