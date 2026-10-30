// The HR admin app (/hrms-admin): same deps and shared components as the sales app,
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

// The dev server's SPA fallback serves index.html (sales); send HR routes to hr.html
const hrFallback = {
	name: "hr-html-fallback",
	configureServer(server) {
		server.middlewares.use((req, _res, next) => {
			if (req.url === "/hrms-admin" || req.url.startsWith("/hrms-admin/")) req.url = "/hr.html"
			next()
		})
	},
}

export default defineConfig({
	server: { ...sales.server, port: 8081 },
	plugins: [
		hrFallback,
		vue(),
		frappeui(),
		VitePWA({
			registerType: "autoUpdate",
			strategies: "injectManifest",
			injectRegister: null,
			devOptions: { enabled: true },
			manifest: {
				display: "standalone",
				name: "HR Admin",
				short_name: "HR Admin",
				start_url: "/hrms-admin",
				scope: "/hrms-admin",
				description: "Leave, payroll, claims and people — the HR side of the business",
				theme_color: "#3437ef",
				background_color: "#eef2f6",
				icons,
			},
		}),
	],
	resolve: { alias: { "@": path.resolve(__dirname, "src") } },
	build: {
		...sales.build,
		outDir: "../erp_overrides/public/hr-admin",
		rollupOptions: {
			input: path.resolve(__dirname, "hr.html"),
			output: { manualChunks: { "frappe-ui": ["frappe-ui"] } },
		},
	},
	optimizeDeps: sales.optimizeDeps,
})
