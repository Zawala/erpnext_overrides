import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching"
import { clientsClaim } from "workbox-core"

// App shell only — documents are always fetched live from the server
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.skipWaiting()
clientsClaim()
