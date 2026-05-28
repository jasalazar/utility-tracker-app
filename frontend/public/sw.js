/**
 * Service Worker — handles incoming Web Push notifications and displays
 * a native browser/OS notification via the Notifications API.
 *
 * This file must be served from the root path (/sw.js) so its scope
 * covers the entire origin. Vite copies files from public/ verbatim.
 */

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "Utility Tracker", body: event.data.text() };
  }

  const { title = "Payment Reminder", body = "", url = "/" } = payload;

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/favicon.ico",
      badge: "/favicon.ico",
      data: { url },
      requireInteraction: false,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.includes(url) && "focus" in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) return clients.openWindow(url);
      })
  );
});
