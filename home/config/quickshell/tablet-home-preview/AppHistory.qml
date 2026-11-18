import QtQuick

QtObject {
    property var apps: []
    property var opened: []
    // Keep ItemGrabResult objects alive: their URLs are in-memory Qt images,
    // not files. Shared by both windows so inactive cards retain their content.
    property var previews: ({})
    property var sourceIdentities: ({})
    property bool capturing: false
    function setSource(id, identity) {
        if ((sourceIdentities[id] || "") === identity) return
        const identities = Object.assign({}, sourceIdentities)
        identities[id] = identity
        sourceIdentities = identities
        const next = Object.assign({}, previews)
        delete next[id]
        previews = next
    }
    function capture(id, item, done) {
        const finish = ok => { if (done) done(ok) }
        if (!id || !item || item.width <= 0 || item.height <= 0) { finish(true); return }
        if (capturing) { finish(false); return }
        capturing = true
        const identity = sourceIdentities[id] || ""
        const accepted = item.grabToImage(result => {
            const next = Object.assign({}, previews)
            const current = (sourceIdentities[id] || "") === identity
            if (opened.includes(id) && current) next[id] = result
            previews = next
            capturing = false
            finish(current)
        }, Qt.size(Math.max(1, Math.round(item.width * Math.min(1, 900 / Math.max(item.width, item.height)))),
                   Math.max(1, Math.round(item.height * Math.min(1, 900 / Math.max(item.width, item.height))))))
        if (!accepted) { capturing = false; finish(false) }
    }
    function close(id) {
        opened = opened.filter(value => value !== id)
        const next = Object.assign({}, previews)
        delete next[id]
        previews = next
        const identities = Object.assign({}, sourceIdentities)
        delete identities[id]
        sourceIdentities = identities
    }
    function open(id) {
        if (!apps.some(app => app.id === id)) return
        opened = [id].concat(opened.filter(value => value !== id))
    }
    function restore(ids) {
        if (!Array.isArray(ids)) return
        const valid = []
        for (const id of ids)
            if (typeof id === "string" && apps.some(app => app.id === id) && !valid.includes(id)) valid.push(id)
        opened = valid
    }
    function cards() {
        return opened.map(id => apps.find(app => app.id === id)).filter(app => !!app)
    }
}
