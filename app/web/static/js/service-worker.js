// This is the service worker script, which executes in its own context
// when the browser receives a push message.

const CACHE_NAME = "notification-app-v1";
const STATIC_ASSETS = [
  "/static/img/notification/icon.png",
  "/static/js/notification-manager.js",
  "/static/js/notification-settings.js",
  "/static/js/push-client.js",
];

// Service Worker for handling notifications
self.addEventListener("install", (event) => {
  console.log("[Service Worker] Installing Service Worker...", event);

  // Cache static assets
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        console.log("[Service Worker] Caching static assets");
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log("[Service Worker] Skip waiting");
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error("[Service Worker] Cache installation failed:", error);
      }),
  );
});

self.addEventListener("activate", (event) => {
  console.log("[Service Worker] Activating Service Worker...", event);

  // Clean up old caches
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => cacheName !== CACHE_NAME)
            .map((cacheName) => {
              console.log("[Service Worker] Deleting old cache:", cacheName);
              return caches.delete(cacheName);
            }),
        );
      })
      .then(() => {
        console.log("[Service Worker] Claiming clients");
        return self.clients.claim();
      })
      .catch((error) => {
        console.error("[Service Worker] Activation failed:", error);
      }),
  );
});

self.addEventListener("push", function (event) {
  console.log("[Service Worker] Push Received.");

  if (!event.data) {
    console.warn("[Service Worker] Push event has no data");
    return;
  }

  let data = {};
  try {
    data = event.data.json();
    console.log("[Service Worker] Push data:", data);
  } catch (e) {
    console.error("[Service Worker] Error parsing push data:", e);
    data = {
      title: "Notification",
      body: event.data.text(),
    };
  }

  const title = data.title || "Push Notification";
  const options = {
    body: data.body || "Something new happened!",
    icon: "/static/img/notification/icon.png",
    data: data.data || {},
    requireInteraction: data.requireInteraction || false,
    actions: data.actions || [
      {
        action: "view",
        title: "View",
      },
      {
        action: "dismiss",
        title: "Dismiss",
      },
    ],
    vibrate: [100, 50, 100],
    timestamp: Date.now(),
  };

  event.waitUntil(
    self.registration.showNotification(title, options).catch((error) => {
      console.error("[Service Worker] Error showing notification:", error);
      // Try to show a fallback notification
      return self.registration.showNotification("New Notification", {
        body: "You have a new notification. Click to view.",
        icon: "/static/img/notification/icon.png",
      });
    }),
  );
});

self.addEventListener("notificationclick", function (event) {
  console.log("[Service Worker] Notification click Received.");

  // Close the notification
  event.notification.close();

  // Handle notification click
  event.waitUntil(
    (async () => {
      try {
        if (event.action === "view") {
          // Handle view action
          if (event.notification.data && event.notification.data.post_url) {
            const url = event.notification.data.post_url;
            const clients = await self.clients.matchAll({
              type: "window",
              includeUncontrolled: true,
            });

            // Check if any window is already open with this URL
            for (const client of clients) {
              if (client.url === url && "focus" in client) {
                await client.focus();
                return;
              }
            }

            // If no window is open, open a new one
            if (self.clients.openWindow) {
              await self.clients.openWindow(url);
            }
          } else {
            // Default to dashboard if no URL
            const clients = await self.clients.matchAll({
              type: "window",
              includeUncontrolled: true,
            });

            // Check if any window is already open
            for (const client of clients) {
              if (client.url.includes("/dashboard") && "focus" in client) {
                await client.focus();
                return;
              }
            }

            // If no window is open, open dashboard
            if (self.clients.openWindow) {
              await self.clients.openWindow("/dashboard");
            }
          }
        } else if (event.action === "dismiss") {
          // Handle dismiss action
          console.log("[Service Worker] Notification dismissed");
        } else {
          // Default click behavior - use post URL if available
          const url = event.notification.data?.post_url || "/dashboard";
          const clients = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
          });

          // Check if any window is already open with this URL
          for (const client of clients) {
            if (client.url === url && "focus" in client) {
              await client.focus();
              return;
            }
          }

          // If no window is open, open the target URL
          if (self.clients.openWindow) {
            await self.clients.openWindow(url);
          }
        }
      } catch (error) {
        console.error(
          "[Service Worker] Error handling notification click:",
          error,
        );
        // Fallback to opening dashboard
        const clients = await self.clients.matchAll({
          type: "window",
          includeUncontrolled: true,
        });

        // Check if any window is already open
        for (const client of clients) {
          if (client.url.includes("/dashboard") && "focus" in client) {
            await client.focus();
            return;
          }
        }

        // If no window is open, open dashboard
        if (self.clients.openWindow) {
          await self.clients.openWindow("/dashboard");
        }
      }
    })(),
  );
});

// Handle service worker updates
self.addEventListener("message", function (event) {
  if (event.data && event.data.type === "SKIP_WAITING") {
    console.log("[Service Worker] Skip waiting message received");
    self.skipWaiting();
  }
});

// Handle fetch events for caching
self.addEventListener("fetch", function (event) {
  // Only handle GET requests
  if (event.request.method !== "GET") return;

  // Check if the request is for a static asset
  const isStaticAsset = STATIC_ASSETS.some((asset) =>
    event.request.url.endsWith(asset),
  );

  if (isStaticAsset) {
    event.respondWith(
      caches
        .match(event.request)
        .then((response) => {
          if (response) {
            return response;
          }
          return fetch(event.request).then((response) => {
            // Cache the response
            const responseToCache = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
            return response;
          });
        })
        .catch((error) => {
          console.error("[Service Worker] Fetch failed:", error);
          // Return a fallback response if available
          return caches.match("/static/img/notification/icon.png");
        }),
    );
  }
});
