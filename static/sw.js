self.addEventListener('install', (e) => {
  console.log('[Service Worker] Install');
});

self.addEventListener('fetch', (e) => {
  // Erforderlich für PWA-Erkennung, leitet Anfragen einfach weiter
  e.respondWith(fetch(e.request));
});