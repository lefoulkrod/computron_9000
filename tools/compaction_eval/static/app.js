/**
 * Alpine.js data component for the compaction eval app.
 */
function evalApp() {
    return {
        // Global state
        models: [],
        records: [],
        filteredRecords: [],
        filter: '',
        selected: null,
        detail: null,
        tab: 'viewer',

        // Settings (persisted to localStorage)
        settings: {
            model: '',
            num_ctx: 32768,
            num_predict: 8192,
            temperature: 0.3,
        },

        // Facts tab
        factsResult: null,
        factsLoading: false,
        factsError: '',

        // Judge tab
        judgeResult: null,
        judgeLoading: false,
        judgeError: '',

        // Compare tab
        compareModel: '',
        compareTemp: 0.3,
        compareCtx: 32768,
        comparePredict: 8192,
        comparePrompt: '',
        compareVariants: [],
        compareLoading: false,
        compareError: '',
        selectedVariant: -1,

        // Probe tab
        probeResult: null,
        probeLoading: false,
        probeError: '',

        async init() {
            this.loadSettings();
            await Promise.all([this.fetchModels(), this.fetchRecords()]);
        },

        // -- Settings persistence --

        loadSettings() {
            try {
                const saved = localStorage.getItem('compaction-eval-settings');
                if (saved) Object.assign(this.settings, JSON.parse(saved));
            } catch { /* ignore */ }
        },

        saveSettings() {
            try {
                localStorage.setItem('compaction-eval-settings', JSON.stringify(this.settings));
            } catch { /* ignore */ }
        },

        // -- Data fetching --

        async fetchModels() {
            try {
                const resp = await fetch('/api/models');
                const data = await resp.json();
                this.models = data.models || [];
            } catch (e) {
                console.error('Failed to fetch models:', e);
            }
        },

        async fetchRecords() {
            try {
                const resp = await fetch('/api/records');
                this.records = await resp.json();
                this.filterRecords();
            } catch (e) {
                console.error('Failed to fetch records:', e);
            }
        },

        filterRecords() {
            const q = this.filter.toLowerCase();
            if (!q) {
                this.filteredRecords = this.records;
                return;
            }
            this.filteredRecords = this.records.filter(r =>
                r.conversation_id.toLowerCase().includes(q) ||
                r.agent_name.toLowerCase().includes(q) ||
                (r.source_history || '').toLowerCase().includes(q)
            );
        },

        async selectRecord(record) {
            this.selected = record;
            this.detail = null;
            this.resetTabState();
            try {
                const resp = await fetch(`/api/records/${record.conversation_id}/${record.id}`);
                this.detail = await resp.json();
            } catch (e) {
                console.error('Failed to fetch record detail:', e);
            }
        },

        resetTabState() {
            this.factsResult = null;
            this.factsError = '';
            this.judgeResult = null;
            this.judgeError = '';
            this.compareVariants = [];
            this.compareError = '';
            this.probeResult = null;
            this.probeError = '';
        },

        // -- Helpers --

        _getModel() {
            return this.settings.model;
        },

        _getOptions(overrides = {}) {
            const opts = {};
            const s = this.settings;
            if (s.num_ctx) opts.num_ctx = s.num_ctx;
            if (s.num_predict) opts.num_predict = s.num_predict;
            if (s.temperature !== '' && s.temperature !== undefined) opts.temperature = s.temperature;
            return { ...opts, ...overrides };
        },

        _baseBody(overrides = {}) {
            return {
                record_id: this.selected.id,
                conversation_id: this.selected.conversation_id,
                model: this._getModel(),
                ...this._getOptions(),
                ...overrides,
            };
        },

        // -- Facts --

        async runFactExtraction() {
            if (!this._getModel()) { this.factsError = 'Select a model first'; return; }
            this.factsLoading = true;
            this.factsError = '';
            this.factsResult = null;
            try {
                const resp = await fetch('/api/extract-facts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this._baseBody()),
                });
                this.factsResult = await resp.json();
                if (this.factsResult.error && !this.factsResult.raw_response) {
                    this.factsError = this.factsResult.error;
                }
            } catch (e) {
                this.factsError = e.message;
            } finally {
                this.factsLoading = false;
            }
        },

        // -- Judge --

        async runJudge() {
            if (!this._getModel()) { this.judgeError = 'Select a model first'; return; }
            this.judgeLoading = true;
            this.judgeError = '';
            this.judgeResult = null;
            try {
                const resp = await fetch('/api/judge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this._baseBody()),
                });
                this.judgeResult = await resp.json();
                if (this.judgeResult.error && !this.judgeResult.raw_response) {
                    this.judgeError = this.judgeResult.error;
                }
            } catch (e) {
                this.judgeError = e.message;
            } finally {
                this.judgeLoading = false;
            }
        },

        // -- Compare --

        async runRecompact() {
            const model = this.compareModel || this._getModel();
            if (!model) { this.compareError = 'Select a model first'; return; }
            this.compareLoading = true;
            this.compareError = '';
            try {
                const body = {
                    record_id: this.selected.id,
                    conversation_id: this.selected.conversation_id,
                    model: model,
                };
                if (this.compareCtx) body.num_ctx = this.compareCtx;
                if (this.comparePredict) body.num_predict = this.comparePredict;
                if (this.compareTemp !== '' && this.compareTemp !== undefined) body.temperature = this.compareTemp;
                if (this.comparePrompt.trim()) body.custom_prompt = this.comparePrompt.trim();

                const resp = await fetch('/api/recompact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const result = await resp.json();
                if (result.error) {
                    this.compareError = result.error;
                } else {
                    this.compareVariants.push({
                        model: model,
                        text: result.summary_text,
                        elapsed: result.elapsed_seconds,
                    });
                }
            } catch (e) {
                this.compareError = e.message;
            } finally {
                this.compareLoading = false;
            }
        },

        // -- Probe --

        async runProbe() {
            if (!this._getModel()) { this.probeError = 'Select a model first'; return; }
            this.probeLoading = true;
            this.probeError = '';
            this.probeResult = null;
            try {
                const resp = await fetch('/api/continuation-probe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this._baseBody()),
                });
                this.probeResult = await resp.json();
                if (this.probeResult.error && !this.probeResult.raw_response) {
                    this.probeError = this.probeResult.error;
                }
            } catch (e) {
                this.probeError = e.message;
            } finally {
                this.probeLoading = false;
            }
        },
    };
}
