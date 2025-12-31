const CACHE_NAME = 'keiba-ev-v1';
const urlsToCache = [
    '/',
    '/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // ネットワーク優先、キャッシュをフォールバック
                return fetch(event.request)
                    .then(networkResponse => {
                        return networkResponse;
                    })
                    .catch(() => response);
            })
    );
});
