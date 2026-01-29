// service-worker.js
const CACHE_NAME = 'anapath-cache-v3';
const APP_VERSION = '1.0.0';

// Fichiers essentiels à mettre en cache
const CORE_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192x192.png',
  './icons/icon-512x512.png',
  './Offline.html'
];

// Installation - seulement mettre en cache les fichiers essentiels
self.addEventListener('install', (event) => {
  console.log(`[Service Worker] Installation v${APP_VERSION}`);
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Mise en cache des fichiers de base');
        return cache.addAll(CORE_ASSETS.map(url => {
          return new Request(url, { mode: 'no-cors' });
        })).catch(error => {
          console.log('[Service Worker] Erreur lors de la mise en cache:', error);
        });
      })
      .then(() => self.skipWaiting())
  );
});

// Activation - nettoyer les anciens caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activation');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log(`[Service Worker] Suppression ancien cache: ${cacheName}`);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Stratégie de cache: Cache First, Network Fallback
self.addEventListener('fetch', (event) => {
  // Ignorer les requêtes non-GET et les requêtes vers l'API
  if (event.request.method !== 'GET' || 
      event.request.url.includes('/api/') ||
      event.request.url.includes('anapath.onrender.com')) {
    return;
  }
  
  event.respondWith(
    caches.match(event.request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          console.log(`[Service Worker] Servi depuis le cache: ${event.request.url}`);
          return cachedResponse;
        }
        
        // Si pas en cache, faire la requête réseau
        return fetch(event.request)
          .then((networkResponse) => {
            // Ne pas mettre en cache les requêtes cross-origin en mode 'no-cors'
            if (!networkResponse || networkResponse.status !== 200 || 
                networkResponse.type === 'opaque' ||
                event.request.url.startsWith('chrome-extension://') ||
                event.request.url.includes('cdn.tailwindcss.com')) {
              return networkResponse;
            }
            
            // Mettre en cache la réponse
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME)
              .then((cache) => {
                cache.put(event.request, responseToCache);
              });
            
            return networkResponse;
          })
          .catch((error) => {
            console.log(`[Service Worker] Erreur réseau pour ${event.request.url}:`, error);
            
            // Pour les pages HTML, retourner la page hors ligne
            if (event.request.destination === 'document' ||
                event.request.headers.get('accept')?.includes('text/html')) {
              return caches.match('./Offline.html');
            }
            
            // Pour les images, retourner une icône par défaut
            if (event.request.destination === 'image') {
              return caches.match('./icons/icon-192x192.png');
            }
            
            // Pour les CSS, retourner un CSS minimal
            if (event.request.destination === 'style') {
              return new Response(`
                body { font-family: Arial, sans-serif; padding: 20px; }
                .offline-message { color: #666; text-align: center; margin-top: 50px; }
              `, { headers: { 'Content-Type': 'text/css' } });
            }
            
            return new Response('Hors ligne', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({ 'Content-Type': 'text/plain' })
            });
          });
      })
  );
});

// Gestion des messages
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.source.postMessage({
      type: 'VERSION_INFO',
      version: APP_VERSION,
      cacheName: CACHE_NAME
    });
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    caches.delete(CACHE_NAME)
      .then(() => {
        console.log('[Service Worker] Cache vidé');
        event.source.postMessage({ type: 'CACHE_CLEARED' });
      });
  }
});
