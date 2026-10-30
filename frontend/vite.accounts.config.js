// The accounts app (/accounts): same deps and shared components as the sales and HR apps,
// its own entry, manifest and output folder.
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { VitePWA } from "vite-plugin-pwa"
import frappeui from "frappe-ui/vite"
import path from "path"

import sales from "./vite.config.js"

const icons = [192, 512].flatMap((size) =>
	["any", "maskable"].map((purpose) => ({
		src: `/assets/erp_overrides/manifest/manifest-icon-${size}.maskable.png`,
		sizes: `${size}x${size}`,
		type: "image/png",
		purpose,
	}))
)

// The dev server's SPA fallback serves index.html (sales); send accounts routes to accounts.html
const accountsFallback = {
	name: "accounts-html-fallback",
	configureServer(server) {
		server.middlewares.use((req, _res, next) => {
			if (req.url === "/accounts" || req.url.startsWith("/accounts/")) req.url = "/accounts.html"
			next()
		})
	},
}

export default defineConfig({
	server: { ...sales.server, port: 8082 },
	plugins: [
		accountsFallback,
		vue(),
		frappeui(),
		VitePWA({
			registerType: "autoUpdate",
			strategies: "injectManifest",
			injectRegister: null,
			devOptions: { enabled: true },
			manifest: {
				display: "standalone",
				name: "Accounts",
				short_name: "Accounts",
				start_url: "/accounts",
				scope: "/accounts",
				description: "Banks, money owed and cash — the accounts side of the business",
				theme_color: "#3437ef",
				background_color: "#eef2f6",
				icons,
			},
		}),
	],
	resolve: { alias: { "@": path.resolve(__dirname, "src") } },
	build: {
		...sales.build,
		outDir: "../erp_overrides/public/accounts",
		rollupOptions: {
			input: path.resolve(__dirname, "accounts.html"),
			output: { manualChunks: { "frappe-ui": ["frappe-ui"] } },
		},
	},
	optimizeDeps: sales.optimizeDeps,
})
