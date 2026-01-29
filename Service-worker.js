const CACHE_NAME = 'anapath-v1.0.0';
const RUNTIME_CACHE = 'anapath-runtime';

// Ressources essentielles à mettre en cache
const STATIC_CACHE_URLS = [
  '/',
  '/index.html',
  '/selection.html',
  '/templates.html',
  '/ARTICLE.html',
  '/params.html',
  '/payement.html',
  'https://cdn.tailwindcss.com',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.5.31/jspdf.plugin.autotable.min.js'
];

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installation en cours...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Mise en cache des ressources statiques');
        return cache.addAll(STATIC_CACHE_URLS);
      })
      .then(() => {
        console.log('[Service Worker] Installation terminée');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[Service Worker] Erreur lors de l\'installation:', error);
      })
  );
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activation en cours...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => {
              return cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE;
            })
            .map((cacheName) => {
              console.log('[Service Worker] Suppression du cache obsolète:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => {
        console.log('[Service Worker] Activation terminée');
        return self.clients.claim();
      })
  );
});

// Stratégie de cache : Network First avec fallback sur Cache
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Ne pas mettre en cache les requêtes API
  if (url.origin === 'https://anapath.onrender.com') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cloner la réponse pour la mettre en cache
          const responseClone = response.clone();
          
          caches.open(RUNTIME_CACHE).then((cache) => {
            cache.put(request, responseClone);
          });
          
          return response;
        })
        .catch(() => {
          // En cas d'échec réseau, essayer le cache
          return caches.match(request);
        })
    );
    return;
  }

  // Pour les autres ressources : Cache First avec mise à jour en arrière-plan
  event.respondWith(
    caches.match(request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          // Retourner la réponse en cache et mettre à jour en arrière-plan
          event.waitUntil(
            fetch(request).then((response) => {
              return caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, response);
              });
            }).catch(() => {
              // Ignorer les erreurs de mise à jour
            })
          );
          
          return cachedResponse;
        }

        // Si pas en cache, récupérer depuis le réseau
        return fetch(request)
          .then((response) => {
            // Vérifier si la réponse est valide
            if (!response || response.status !== 200 || response.type === 'error') {
              return response;
            }

            // Cloner la réponse pour la mettre en cache
            const responseClone = response.clone();

            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });

            return response;
          })
          .catch((error) => {
            console.error('[Service Worker] Erreur lors du fetch:', error);
            
            // Retourner une page d'erreur personnalisée si disponible
            return caches.match('/offline.html').catch(() => {
              return new Response('Vous êtes hors ligne', {
                status: 503,
                statusText: 'Service Unavailable',
                headers: new Headers({
                  'Content-Type': 'text/plain'
                })
              });
            });
          });
      })
  );
});

// Gestion des messages du client
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            return caches.delete(cacheName);
          })
        );
      }).then(() => {
        console.log('[Service Worker] Cache vidé');
        self.clients.matchAll().then(clients => {
          clients.forEach(client => client.postMessage({
            type: 'CACHE_CLEARED'
          }));
        });
      })
    );
  }
});

// Notification de mise à jour disponible
self.addEventListener('controllerchange', () => {
  self.clients.matchAll().then(clients => {
    clients.forEach(client => client.postMessage({
      type: 'UPDATE_AVAILABLE'
    }));
  });
});

// Synchronisation en arrière-plan (Background Sync)
self.addEventListener('sync', (event) => {
  console.log('[Service Worker] Synchronisation en arrière-plan:', event.tag);
  
  if (event.tag === 'sync-comptes-rendus') {
    event.waitUntil(
      syncComptesRendus()
    );
  }
});

// Fonction de synchronisation des comptes rendus
async function syncComptesRendus() {
  try {
    // Récupérer les données en attente de synchronisation depuis IndexedDB
    // Cette fonction devra être implémentée selon vos besoins
    console.log('[Service Worker] Synchronisation des comptes rendus...');
    return Promise.resolve();
  } catch (error) {
    console.error('[Service Worker] Erreur lors de la synchronisation:', error);
    return Promise.reject(error);
  }
}

// Gestion des notifications push
self.addEventListener('push', (event) => {
  console.log('[Service Worker] Notification Push reçue:', event);
  
  const options = {
    body: event.data ? event.data.text() : 'Nouvelle notification ANAPATH',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    tag: 'anapath-notification',
    requireInteraction: false
  };

  event.waitUntil(
    self.registration.showNotification('ANAPATH ELYOUSR', options)
  );
});

// Gestion des clics sur les notifications
self.addEventListener('notificationclick', (event) => {
  console.log('[Service Worker] Notification cliquée:', event.notification.tag);
  
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Si une fenêtre est déjà ouverte, la focaliser
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if ('focus' in client) {
            return client.focus();
          }
        }
        
        // Sinon, ouvrir une nouvelle fenêtre
        if (clients.openWindow) {
          return clients.openWindow('/');
        }
      })
  );
});
