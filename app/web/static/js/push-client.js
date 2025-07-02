// PUSH_VAPID_PUBLIC_KEY will be set globally in the HTML before this script is loaded.
// Alternatively, consider passing it via a data attribute or a more structured approach.

(() => {
  const MAX_RETRY_ATTEMPTS = 3;
  const RETRY_DELAY = 1000; // 1 second
  // Fetch CSRF token from meta tag without clashing with other scripts
  const csrfTokenElementPush = document.querySelector(
    'meta[name="csrf-token"]',
  );
  const CSRF_TOKEN_PUSH = csrfTokenElementPush
    ? csrfTokenElementPush.getAttribute("content")
    : "";

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/-/g, "+")
      .replace(/_/g, "/");

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function retryOperation(operation, maxAttempts = MAX_RETRY_ATTEMPTS) {
    let lastError;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error;
        console.warn(
          `Operation failed (attempt ${attempt}/${maxAttempts}):`,
          error,
        );
        if (attempt < maxAttempts) {
          await sleep(RETRY_DELAY * attempt);
        }
      }
    }
    throw lastError;
  }

  async function cleanupOldSubscriptions() {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
          try {
            await subscription.unsubscribe();
            console.log("Unsubscribed from old push subscription");
          } catch (error) {
            console.warn("Error unsubscribing:", error);
          }
        }
      }
    } catch (error) {
      console.warn("Error cleaning up old subscriptions:", error);
    }
  }

  async function registerServiceWorkerAndSubscribe() {
    if (!("serviceWorker" in navigator && "PushManager" in window)) {
      console.warn("Push messaging is not supported");
      showError("Push notifications are not supported in your browser.");
      return;
    }

    console.log("Service Worker and Push is supported");

    try {
      // Register service worker with retry
      const swRegistration = await retryOperation(async () => {
        const registration = await navigator.serviceWorker.register(
          "/static/js/service-worker.js",
        );
        console.log("Service Worker is registered", registration);
        return registration;
      });

      // Request permission
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        console.warn("Permission for notifications was not granted.");
        showError("Please enable notifications to receive updates.");
        return;
      }
      console.log("Notification permission granted.");

      // Get or create subscription
      let subscription = await swRegistration.pushManager.getSubscription();
      if (subscription === null) {
        console.log("Not subscribed, attempting to subscribe...");
        if (typeof PUSH_VAPID_PUBLIC_KEY === "undefined" || !PUSH_VAPID_PUBLIC_KEY) {
          console.error("VAPID public key is not defined. Cannot subscribe.");
          showError("Push notification setup error: Missing VAPID public key.");
          return;
        }

        // Subscribe with retry
        subscription = await retryOperation(async () => {
          return await swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(PUSH_VAPID_PUBLIC_KEY),
          });
        });
        console.log("New subscription obtained:", subscription);
      } else {
        console.log("Already subscribed:", subscription);
      }        // POST subscription to backend with retry
        await retryOperation(async () => {
          const response = await fetch("/api/subscriptions", {
            method: "POST",
            body: JSON.stringify(subscription),
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": CSRF_TOKEN_PUSH,
            },
          });

          if (!response.ok) {
            throw new Error(`Failed to save subscription: ${response.status}`);
          }

          console.log("Subscription sent to server.");
        });

      // Set up subscription expiration handling
      setupSubscriptionExpirationHandling(subscription);
    } catch (error) {
      console.error("Service Worker or Subscription Error", error);
      showError(
        "Failed to set up push notifications. See console for details.",
      );
    }
  }

  function setupSubscriptionExpirationHandling(subscription) {
    if (!subscription) return;

    // Check subscription expiration every hour
    setInterval(async () => {
      try {
        const currentSubscription =
          await subscription.pushManager.getSubscription();
        if (!currentSubscription) {
          console.log("Subscription expired, resubscribing...");
          await registerServiceWorkerAndSubscribe();
        }
      } catch (error) {
        console.warn("Error checking subscription:", error);
      }
    }, 3600000); // 1 hour
  }

  function showError(message) {
    // Create error toast if it doesn't exist
    let toast = document.getElementById("error-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "error-toast";
      toast.className =
        "fixed bottom-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded";
      document.body.appendChild(toast);
    }

    // Show error message
    toast.textContent = message;
    toast.style.display = "block";

    // Hide after 5 seconds
    setTimeout(() => {
      toast.style.display = "none";
    }, 5000);
  }

  async function unregisterServiceWorkerAndUnsubscribe() {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
          // Remove subscription from server
          try {
            const response = await fetch("/api/subscriptions", {
              method: "DELETE",
              body: JSON.stringify(subscription),
              headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": CSRF_TOKEN_PUSH,
              },
            });
            if (response.ok) {
              console.log("Subscription removed from server");
            }
          } catch (error) {
            console.warn("Failed to remove subscription from server:", error);
          }

          await subscription.unsubscribe();
          console.log("Unsubscribed from push notifications");
        }
        await registration.unregister();
        console.log("Unregistered service worker");
      }
    } catch (error) {
      console.error("Error unregistering service worker:", error);
      showError("Failed to disable notifications. See console for details.");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (Notification.permission === "granted") {
      registerServiceWorkerAndSubscribe();
    }

    const notifToggle = document.getElementById("notif-toggle");
    if (notifToggle) {
      notifToggle.addEventListener("change", async (event) => {
        if (event.target.checked) {
          await registerServiceWorkerAndSubscribe();
        } else {
          console.log("User disabled notifications via toggle.");
          await unregisterServiceWorkerAndUnsubscribe();
        }
      });
    }

    const testPushBtn = document.getElementById("test-push-btn");
    if (testPushBtn) {
      testPushBtn.addEventListener("click", async () => {
        try {
          const response = await fetch("/notify");
          if (!response.ok) {
            throw new Error(
              `Failed to trigger notification: ${response.status}`,
            );
          }
          const result = await response.json();
          console.log("Notify endpoint response:", result);
          showError(result.message || "Test notification sent");
        } catch (error) {
          console.error("Error calling /notify:", error);
          showError("Error triggering notification. See console.");
        }
      });
    }
  });
})();
