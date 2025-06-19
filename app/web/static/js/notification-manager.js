/**
 * Notification Manager for Web Notifications API
 */
(() => {
  const csrfTokenElement = document.querySelector('meta[name="csrf-token"]');
  const CSRF_TOKEN = csrfTokenElement
    ? csrfTokenElement.getAttribute("content")
    : "";
  class NotificationManager {
    constructor() {
      this.isSupported = "Notification" in window;
      this.permission = this.isSupported ? Notification.permission : "denied";
      this.enabled = this.getStoredPreference();
      this.lastUnreadCount = 0;
      this.activeNotifications = new Map();
      this.updateTimer = null;
      this.initializeEventListeners();
      this.updateUI();
      if (this.enabled && this.permission === "default")
        this.requestPermission();
    }
    isNotificationSupported() {
      return this.isSupported;
    }
    getPermissionStatus() {
      return this.isSupported ? Notification.permission : "denied";
    }
    async requestPermission() {
      if (!this.isSupported) return "denied";
      if (this.permission === "granted") return "granted";
      try {
        this.permission = await Notification.requestPermission();
        this.updateUI();
        if (this.permission === "granted") {
          this.showTestNotification();
          this.startUpdateTimer();
        } else if (this.permission === "denied") {
          this.setEnabled(false);
        }
        return this.permission;
      } catch (error) {
        console.error("Error requesting permission:", error);
        return "denied";
      }
    }
    showTestNotification() {
      this.showNotification({
        title: "✅ Notifications Enabled",
        body: "You will now receive desktop notifications for new posts.",
        icon: "/static/img/notification/icon.png",
        tag: "test-notification",
        requireInteraction: false,
      });
    }
    showNotification(options) {
      if (!this.canShowNotifications()) return null;

      // Check notification settings
      const settings = window.notificationSettings?.getSettings() || {};

      // Don't show if desktop notifications are disabled
      if (!settings.desktopNotifications) return null;

      // Clean up old notification with same tag
      if (options.tag) {
        const oldNotification = this.activeNotifications.get(options.tag);
        if (oldNotification) {
          oldNotification.close();
          this.activeNotifications.delete(options.tag);
        }
      }

      const notificationOptions = {
        icon: "/static/img/notification/icon.png",
        timestamp: Date.now(),
        actions: [
          { action: "view", title: "View" },
          { action: "dismiss", title: "Dismiss" },
        ],
        ...options,
      };

      try {
        const notification = new Notification(
          options.title,
          notificationOptions,
        );

        // Store notification reference
        if (options.tag) {
          this.activeNotifications.set(options.tag, notification);
        }

        // Set up notification event handlers
        notification.onclick = (event) => {
          event.preventDefault();
          this.handleNotificationClick(event, options.data);
        };
        notification.onclose = () => {
          if (options.tag) {
            this.activeNotifications.delete(options.tag);
          }
        };

        // Auto-close non-interactive notifications
        if (!options.requireInteraction) {
          setTimeout(() => {
            if (notification) {
              notification.close();
            }
          }, 10000);
        }

        return notification;
      } catch (error) {
        console.error("Error showing notification:", error);
        return null;
      }
    }
    handleNotificationClick(event, data) {
      event.target.close();
      if (window.focus) window.focus();
      if (data) {
        if (data.post_url) {
          window.open(data.post_url, "_blank");
        } else if (data.post_ids && data.post_ids.length > 0) {
          this.scrollToPostsSection();
        }
      }
    }
    scrollToPostsSection() {
      const postsSection = document.getElementById("postsSection");
      if (postsSection) postsSection.scrollIntoView({ behavior: "smooth" });
    }
    showNewPostsNotification(newPostsCount, posts = []) {
      if (newPostsCount === 0) return;
      let notificationData;
      if (posts.length === 1) {
        const post = posts[0];
        notificationData = {
          title: post.is_urgent ? "🚨 URGENT POST" : "📢 New Post",
          body: `${post.title}\n${post.content ? post.content.substring(0, 100) + "..." : ""}`,
          tag: `post-${post.id}`,
          requireInteraction: post.is_urgent,
          data: {
            post_id: post.id,
            post_url: post.link,
            is_urgent: post.is_urgent,
          },
        };
      } else {
        const urgentCount = posts.filter((p) => p.is_urgent).length;
        const title =
          urgentCount > 0
            ? `🚨 ${urgentCount} URGENT + ${newPostsCount - urgentCount} new posts`
            : `📢 ${newPostsCount} new posts available`;
        const body =
          posts
            .slice(0, 3)
            .map((p) => `${p.is_urgent ? "🚨" : "•"} ${p.title}`)
            .join("\n") +
          (posts.length > 3 ? `\n... and ${posts.length - 3} more` : "");
        notificationData = {
          title,
          body,
          tag: "bulk-posts",
          requireInteraction: urgentCount > 0,
          data: {
            post_count: newPostsCount,
            urgent_count: urgentCount,
            post_ids: posts.map((p) => p.id),
          },
        };
      }
      this.showNotification(notificationData);
    }
    canShowNotifications() {
      return (
        this.isSupported &&
        this.permission === "granted" &&
        this.enabled &&
        !document.hidden
      ); // Don't show notifications when tab is visible
    }
    setEnabled(enabled) {
      this.enabled = enabled;
      this.storePreference(enabled);
      this.updateUI();

      if (enabled) {
        if (this.permission !== "granted") {
          this.requestPermission();
        } else {
          this.startUpdateTimer();
        }
      } else {
        this.stopUpdateTimer();
        this.closeAllNotifications();
      }
    }
    closeAllNotifications() {
      this.activeNotifications.forEach((notification) => {
        notification.close();
      });
      this.activeNotifications.clear();
    }
    getStoredPreference() {
      try {
        const stored = localStorage.getItem("desktopNotificationsEnabled");
        return stored !== null ? JSON.parse(stored) : true;
      } catch (error) {
        console.error("Error reading notification preference:", error);
        return true;
      }
    }
    storePreference(enabled) {
      try {
        localStorage.setItem(
          "desktopNotificationsEnabled",
          JSON.stringify(enabled),
        );
      } catch (error) {
        console.error("Error storing notification preference:", error);
      }
    }
    initializeEventListeners() {
      document.addEventListener("DOMContentLoaded", () => {
        const toggle = document.getElementById("notif-toggle");
        if (toggle) {
          toggle.checked = this.enabled;
          toggle.addEventListener("change", (e) =>
            this.setEnabled(e.target.checked),
          );
        }
        const markBtn = document.getElementById("markAllReadBtn");
        if (markBtn) {
          markBtn.addEventListener("click", () => this.markAllRead());
        }
        this.addPermissionStatusIndicator();
        if (this.enabled && this.permission === "default") {
          setTimeout(() => this.requestPermission(), 1000);
        }
      });
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
          this.checkForUpdates();
        }
      });
      if (this.isSupported) {
        // Use navigator.permissions API to watch for permission changes
        if (navigator.permissions && navigator.permissions.query) {
          navigator.permissions
            .query({ name: "notifications" })
            .then((permissionStatus) => {
              permissionStatus.addEventListener("change", () => {
                this.permission = Notification.permission;
                this.updateUI();
                if (this.permission === "denied") {
                  this.setEnabled(false);
                }
              });
            });
        }
      }
    }
    startUpdateTimer() {
      this.stopUpdateTimer(); // Clear any existing timer

      const updateInterval = (window.POLLING_INTERVAL_MINUTES || 5) * 60 * 1000; // Convert minutes to milliseconds

      this.updateTimer = setInterval(() => {
        if (this.canShowNotifications()) {
          this.checkForUpdates();
        }
      }, updateInterval);
    }
    stopUpdateTimer() {
      if (this.updateTimer) {
        clearInterval(this.updateTimer);
        this.updateTimer = null;
      }
    }
    addPermissionStatusIndicator() {
      const toggle = document.getElementById("notif-toggle");
      if (!toggle) return;
      const container =
        toggle.closest(".form-check-label") || toggle.parentElement;
      let indicator = container.querySelector(".permission-indicator");
      if (!indicator) {
        indicator = document.createElement("small");
        indicator.className = "permission-indicator ms-2";
        container.appendChild(indicator);
      }
      this.updatePermissionIndicator(indicator);
    }
    updatePermissionIndicator(indicator) {
      if (!indicator) return;
      const status = this.getPermissionStatus();
      const enabled = this.enabled;
      let text = "",
        className = "text-muted";
      if (!this.isSupported) {
        text = "(Not supported)";
        className = "text-warning";
      } else if (status === "denied") {
        text = "(Blocked)";
        className = "text-danger";
      } else if (status === "granted" && enabled) {
        text = "(Active)";
        className = "text-success";
      } else if (status === "default") {
        text = "(Click to enable)";
        className = "text-info";
      }
      indicator.textContent = text;
      indicator.className = `permission-indicator ms-2 ${className}`;
    }
    updateUI() {
      const toggle = document.getElementById("notif-toggle");
      if (toggle) {
        toggle.checked = this.enabled;
        toggle.disabled = !this.isSupported;
      }
      const indicator = document.querySelector(".permission-indicator");
      if (indicator) this.updatePermissionIndicator(indicator);
    }
    async checkForUpdates() {
      if (!this.canShowNotifications()) return;

      try {
        const settings = window.notificationSettings?.getSettings() || {};

        const response = await fetch("/api/notifications/status", {
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
          },
        });

        if (!response.ok) {
          throw new Error(
            `Failed to fetch notification status: ${response.status}`,
          );
        }

        const data = await response.json();
        this.updateNotificationBadge(data.unread_count);

        if (
          data.unread_count > this.lastUnreadCount &&
          data.latest_notifications
        ) {
          const newCount = data.unread_count - this.lastUnreadCount;
          const newNotifs = data.latest_notifications
            .slice(0, newCount)
            .reverse();

          // Filter notifications based on settings
          const filteredNotifs = newNotifs;

          filteredNotifs.forEach((notif) => {
            this.showNotification({
              title: notif.message,
              body: notif.message,
              tag: `notif-${notif.id}`,
              requireInteraction: notif.is_urgent,
              data: {
                post_id: notif.post_id,
                is_urgent: notif.is_urgent,
              },
            });
          });
        }
        this.lastUnreadCount = data.unread_count;
      } catch (error) {
        console.error("Error checking for updates:", error);
        // Don't show error notification to avoid spamming the user
      }
    }
    updateNotificationBadge(count) {
      const badge = document.querySelector(".notification-badge");
      if (badge) {
        if (count > 0) {
          badge.textContent = count;
          badge.style.display = "inline";
        } else {
          badge.style.display = "none";
        }
      }
    }

    async markAllRead() {
      try {
        const resp = await fetch("/api/notifications/mark-read", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "X-CSRFToken": CSRF_TOKEN,
          },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data.success) {
          this.updateNotificationBadge(0);
          const container = document.getElementById("notifications-content");
          if (container) {
            container.innerHTML =
              `<p class="text-gray-500 text-sm text-center py-8">` +
              `<i class="fas fa-inbox text-xl mb-2 block"></i>No new notifications</p>`;
          }
          window.newPostsCount = 0;
          const newBadge = document.getElementById("newPostsBadge");
          if (newBadge) newBadge.style.display = "none";
        }
      } catch (err) {
        console.error("Failed to mark notifications read:", err);
      }
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    window.notificationManager = new NotificationManager();
    if (notificationManager.canShowNotifications()) {
      notificationManager.checkForUpdates();
      notificationManager.startUpdateTimer();
    }
  });
  window.NotificationManager = NotificationManager;
})();
