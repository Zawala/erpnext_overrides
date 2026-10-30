import { reactive } from "vue"

// Bumped after a save/submit so open lists refetch
export const listVersions = reactive({})
export const bumpList = (doctype) => (listVersions[doctype] = (listVersions[doctype] || 0) + 1)
