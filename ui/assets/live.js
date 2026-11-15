// The bundled renderer instantiates this class. DesktopWindow supplies the
// original view, labels, platform detection, artwork and theme transitions.
class Component extends DesktopWindow {
    constructor(props) {
        super(props);
        this.state = {...this.state, items: [], hist: []};
        this.writes = Promise.resolve();
        this.pendingWrites = 0;
        this.revision = 0;
    }

    componentDidMount() {
        this.mounted = true;
        this.ready = () => this.refresh();
        window.addEventListener("pywebviewready", this.ready);
        this.ready();
        this.pollTimer = setInterval(this.ready, 450);
    }

    componentWillUnmount() {
        this.mounted = false;
        window.removeEventListener("pywebviewready", this.ready);
        clearInterval(this.pollTimer);
        clearTimeout(this._s);
    }

    applySnapshot(snapshot) {
        const serialized = JSON.stringify(snapshot);
        if (serialized === this.lastSnapshot) return;
        this.lastSnapshot = serialized;
        const {theme, dir, par, thr, items, hist, preview} = snapshot;
        const update = {theme, dir, par, thr, items, hist, preview};
        if (this.state.draft === this.state.dir) update.draft = dir;
        this.setState(update);
    }

    async refresh() {
        const api = window.pywebview?.api;
        if (!api?.snapshot || this.polling || this.pendingWrites) return;
        const revision = this.revision;
        this.polling = true;
        try {
            const snapshot = await api.snapshot(this.state.url.trim());
            if (this.mounted && revision === this.revision) this.applySnapshot(snapshot);
            this.pollError = "";
        } catch (error) {
            const message = error.message || String(error);
            if (this.mounted && this.pollError !== message) this.flash(message);
            this.pollError = message;
        } finally {
            this.polling = false;
        }
    }

    command(method, args, onSuccess, onError) {
        // Serialize actions. A snapshot started before a click must never undo it.
        this.pendingWrites++;
        this.revision++;
        this.writes = this.writes.then(async () => {
            if (!this.mounted) return;
            const api = window.pywebview?.api;
            if (!api?.[method]) throw new Error("The desktop connection is not ready yet.");
            const result = await api[method](...args);
            if (result?.error) throw new Error(result.error);
            const snapshot = result?.items ? result : await api.snapshot();
            if (this.mounted) {
                this.applySnapshot(snapshot);
                if (onSuccess) onSuccess(snapshot);
            }
        }).catch(error => {
            if (!this.mounted) return;
            const message = error.message || String(error);
            if (onError) onError(message);
            else this.flash(message);
        }).finally(() => { this.pendingWrites--; });
    }

    renderVals() {
        const view = super.renderVals();
        const s = this.state;
        const preview = s.preview;
        let hint = "Paste a media link, or import a batch file.";
        if (preview && preview.url === s.url.trim()) {
            const engine = preview.spotify ? "spotDL" : "yt-dlp";
            hint = `Detected ${preview.folder} · ${engine} · saves to ${preview.dir}`;
            if (s.video && preview.spotify) hint += " · Spotify is always MP3";
        }
        const pref = (key, value, done) => this.command("set_pref", [key, value], done);
        const items = view.items.map((item, index) => {
            const raw = s.items[index];
            const action = name => this.command("action", [raw.id, name]);
            const row = {...item, plat: raw.folder,
                act: () => action(raw.st === "fail" ? "retry" : raw.st === "done" ? "remove" : "cancel"),
                rm: () => action("remove")
            };
            if (raw.st === "run" && raw.pct == null) {
                row.pct = 0;
                row.status = "Downloading…";
            }
            if (raw.st === "done" && raw.dir) {
                // A successful job can also mean the archive skipped a previous download.
                row.status = "Finished · Target folder " + raw.dir;
            }
            return row;
        });
        return {...view, items, hint,
            toggle: () => pref("theme", s.theme === "light" ? "dark" : "light",
                () => this.flash("Saved theme to data/settings.json")),
            onAdd: () => {
                const url = s.url.trim();
                if (url) this.command("enqueue", [[url], s.video], () => {
                    if (this.state.url.trim() === url) this.setState({url: ""});
                });
            },
            onImport: () => this.command("import_batch", [s.video]),
            onClear: () => this.command("clear_finished", []),
            onSaveDir: () => this.command("save_dir", [s.draft],
                snapshot => this.flash("Saved download_dir to data/settings.json", {draft: snapshot.dir, err: ""}),
                message => this.setState({err: message})),
            parDec: () => pref("par", Math.max(1, s.par - 1)),
            parInc: () => pref("par", Math.min(8, s.par + 1)),
            thrDec: () => pref("thr", Math.max(1, s.thr - 1)),
            thrInc: () => pref("thr", Math.min(16, s.thr + 1))
        };
    }
}
