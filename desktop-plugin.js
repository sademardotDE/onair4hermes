/**
 * onair4hermes — Hermes Desktop Plugin für OnAir (SDR / Funküberwachung).
 *
 * Zeigt den OnAir-Receiver-Status, Geräte, Modi, Telemetrie und Spektrum
 * in der Hermes-Desktop-GUI an und erlaubt Start/Stopp, Modus- und
 * Frequenzwechsel über die OnAir Remote-Control HTTP API
 * (http://127.0.0.1:8765/api/v1/).
 *
 * Save as: <hermes home>/desktop-plugins/onair4hermes/plugin.js
 * Reload: ⌘K / Ctrl+K → "Reload desktop plugins"
 *
 * Plain ESM, loaded uncompiled — UI is jsx() calls, not JSX syntax.
 * Only these imports resolve: @hermes/plugin-sdk, react, react/jsx-runtime.
 */

import { cn, host, Tip, usePluginI18n, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs, useState, useEffect, useRef } from 'react/jsx-runtime'

const ID = 'onair4hermes'
const API_BASE = 'http://127.0.0.1:8765'
const POLL_MS = 3000

// ---------- kleine Helfer ----------

async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(3000) })
    if (!res.ok) return null
    return await res.json()
  } catch {}
  return null
}

async function apiPost(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(3000),
    })
    return res.ok
  } catch {}
  return false
}

// ---------- Strings ----------

function strings(locale) {
  return locale.startsWith('de')
    ? {
        title: 'onair4hermes',
        paneTitle: 'OnAir (SDR)',
        status: 'Status',
        running: 'Läuft',
        stopped: 'Gestoppt',
        offline: 'OnAir API nicht erreichbar',
        device: 'Gerät',
        mode: 'Modus',
        frequency: 'Frequenz',
        sampleRate: 'Sample Rate',
        gain: 'Gain',
        snr: 'SNR',
        quality: 'Qualität',
        locked: 'Gelockt',
        unlocked: 'Nicht gelockt',
        start: '▶ Start',
        stop: '⏹ Stop',
        setMode: 'Modus setzen',
        setFreq: 'Frequenz setzen',
        hz: 'Hz',
        mhz: 'MHz',
        spectrum: 'Spektrum',
        bins: 'Bins',
        noDevices: 'Keine Geräte',
        noModes: 'Keine Modi',
        chipTooltip: 'OnAir SDR Empfänger',
        errorFetch: 'Fehler beim Abruf der OnAir API',
      }
    : {
        title: 'onair4hermes',
        paneTitle: 'OnAir (SDR)',
        status: 'Status',
        running: 'Running',
        stopped: 'Stopped',
        offline: 'OnAir API not reachable',
        device: 'Device',
        mode: 'Mode',
        frequency: 'Frequency',
        sampleRate: 'Sample Rate',
        gain: 'Gain',
        snr: 'SNR',
        quality: 'Quality',
        locked: 'Locked',
        unlocked: 'Unlocked',
        start: '▶ Start',
        stop: '⏹ Stop',
        setMode: 'Set mode',
        setFreq: 'Set frequency',
        hz: 'Hz',
        mhz: 'MHz',
        spectrum: 'Spectrum',
        bins: 'Bins',
        noDevices: 'No devices',
        noModes: 'No modes',
        chipTooltip: 'OnAir SDR Receiver',
        errorFetch: 'Error fetching OnAir API',
      }
}

function getLocale() {
  try {
    const l = typeof document !== 'undefined' ? document.documentElement.lang : ''
    if (typeof l === 'string') {
      if (l.startsWith('de')) return 'de'
      if (l.startsWith('en')) return 'en'
    }
  } catch {}
  return 'en'
}

// ---------- Status Chip ----------

function StatusChip({ t }) {
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const st = await apiGet('/api/v1/status')
      if (!cancelled) setRunning(st && st.running ? true : false)
    })()
    return () => { cancelled = true }
  }, [])

  return jsx(Tip, {
    label: t('chipTooltip'),
    children: jsx('button', {
      className: cn(
        'inline-flex h-full items-center gap-1 px-2 text-[0.6875rem] transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
        running ? 'bg-(--ui-success) text-(--ui-success-foreground)' : ''
      ),
      type: 'button',
      title: running ? t('running') : t('stopped'),
      children: running ? '● OnAir' : '○ OnAir',
    })
  })
}

// ---------- Spektrum Canvas ----------

function SpectrumPlot({ dbfs, centerHz, sampleRateHz }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !dbfs) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const w = rect.width
    const h = rect.height
    const n = dbfs.length

    // Hintergrund
    ctx.fillStyle = 'var(--dt-popover, #ffffff)'
    ctx.fillRect(0, 0, w, h)
    if (typeof document !== 'undefined' && document.documentElement.classList.contains('dark')) {
      ctx.fillStyle = '#1e1e22'
      ctx.fillRect(0, 0, w, h)
    }

    // Achsenlinie
    ctx.strokeStyle = 'rgba(128,128,128,0.3)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, h / 2)
    ctx.lineTo(w, h / 2)
    ctx.stroke()

    // Bars
    const barW = Math.max(1, w / n)
    const maxDb = -20
    const minDb = -90
    for (let i = 0; i < n; i++) {
      const db = dbfs[i]
      const pct = Math.max(0, Math.min(1, (db - minDb) / (maxDb - minDb)))
      const barH = h * pct
      const x = i * barW
      const y = h - barH

      // Farbe: Rot bei Peak, sonst blau/grün
      ctx.fillStyle = db > -40 ? '#f85149' : db > -60 ? '#d29922' : '#58a6ff'
      ctx.fillRect(x, y, Math.max(1, barW - 1), barH)
    }

    // Center-Frequenz Markierung
    ctx.fillStyle = '#a371f7'
    ctx.fillText(`${(centerHz / 1e6).toFixed(1)} MHz`, 4, h - 4)
  }, [dbfs, centerHz, sampleRateHz])

  return jsx('canvas', {
    ref: canvasRef,
    style: { width: '100%', height: '120px', background: 'transparent' },
  })
}

// ---------- Pane ----------

function OnAirPane() {
  const t = usePluginI18n(ID)
  const locale = getLocale()
  const S = strings(locale)

  const [status, setStatus] = useState(null)
  const [devices, setDevices] = useState([])
  const [modes, setModes] = useState([])
  const [telemetry, setTelemetry] = useState(null)
  const [spectrum, setSpectrum] = useState(null)
  const [modeInput, setModeInput] = useState('')
  const [freqInput, setFreqInput] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    let cancelled = false
    let timer
    const tick = async () => {
      const [st, dev, mods, tel, spec] = await Promise.all([
        apiGet('/api/v1/status'),
        apiGet('/api/v1/devices'),
        apiGet('/api/v1/modes'),
        apiGet('/api/v1/telemetry'),
        apiGet('/api/v1/spectrum?bins=64'),
      ])
      if (!cancelled) {
        setStatus(st)
        setDevices(dev || [])
        setModes(mods || [])
        setTelemetry(tel)
        setSpectrum(spec)
      }
    }
    tick()
    timer = setInterval(tick, POLL_MS)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  const handleStart = async () => {
    const ok = await apiPost('/api/v1/start')
    setMsg(ok ? 'Receiver gestartet' : S.errorFetch)
    setTimeout(() => setMsg(''), 2500)
  }

  const handleStop = async () => {
    const ok = await apiPost('/api/v1/stop')
    setMsg(ok ? 'Receiver gestoppt' : S.errorFetch)
    setTimeout(() => setMsg(''), 2500)
  }

  const handleSetMode = async () => {
    const fam = modeInput.trim()
    if (!fam) return
    const num = Number(fam)
    const isNaN = Number.isNaN(num)
    const ok = await apiPost('/api/v1/mode', { family: isNaN ? fam : num })
    setMsg(ok ? `Modus gesetzt: ${fam}` : S.errorFetch)
    setTimeout(() => setMsg(''), 2500)
  }

  const handleSetFreq = async () => {
    const val = freqInput.trim()
    if (!val) return
    if (val.toLowerCase().endsWith('m')) {
      const ok = await apiPost('/api/v1/frequency', { mhz: parseFloat(val.slice(0, -1)) })
      setMsg(ok ? `Frequenz: ${val}` : S.errorFetch)
    } else {
      const ok = await apiPost('/api/v1/frequency', { hz: parseInt(val, 10) })
      setMsg(ok ? `Frequenz: ${val} Hz` : S.errorFetch)
    }
    setTimeout(() => setMsg(''), 2500)
  }

  const st = status || {}
  const tel = telemetry || {}
  const spec = spectrum || {}

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-3 text-sm',
    children: [
      jsx('div', { className: 'font-medium', children: S.paneTitle }),

      // Statuszeile
      jsxs('div', {
        className: 'flex items-center gap-3 mb-1',
        children: [
          jsx('span', {
            className: cn('inline-flex items-center gap-1 px-1.5 py-px rounded text-[10px] font-mono',
              st.running ? 'bg-(--ui-success)/20 text-(--ui-success)' : 'bg-(--chrome-action-hover) text-(--ui-text-tertiary)'),
            children: st.running ? S.running : S.stopped,
          }),
          jsx('span', {
            className: 'text-(--ui-text-tertiary)',
            children: st.device || '—',
          }),
          jsx('span', {
            className: 'text-(--ui-text-tertiary)',
            children: st.mode || '—',
          }),
        ],
      }),

      // Frequenz
      st.frequencyHz != null && jsxs('div', {
        className: 'flex items-center gap-2 mb-1',
        children: [
          jsx('span', { className: 'w-16 text-(--ui-text-secondary)', children: S.frequency + ':' }),
          jsx('span', {
            className: 'font-mono text-(--ui-text-primary)',
            children: `${(st.frequencyHz / 1e6).toFixed(3)} ${S.mhz}`,
          }),
        ],
      }),

      // Telemetrie
      tel.locked != null && jsxs('div', {
        className: 'flex items-center gap-2 mb-1 text-[10px] text-(--ui-text-tertiary)',
        children: [
          jsx('span', {
            className: cn('px-1 py-px rounded', tel.locked ? 'bg-(--ui-success)/20 text-(--ui-success)' : 'bg-(--chrome-action-hover)'),
            children: tel.locked ? S.locked : S.unlocked,
          }),
          tel.snrDb != null && jsx('span', { children: `${S.snr}: ${tel.snrDb.toFixed(1)} dB` }),
          tel.quality?.percent != null && jsx('span', { children: `${S.quality}: ${tel.quality.percent}%` }),
        ],
      }),

      // RDS Info
      tel.details?.psName && jsxs('div', {
        className: 'text-[10px] text-(--ui-text-secondary) mb-1',
        children: `${tel.details.psName || ''}${tel.details.radioText ? ' — ' + tel.details.radioText : ''}`,
      }),

      // Spektrum
      spec.dbfs && jsxs('div', {
        className: 'flex-1 min-h-[120px]',
        children: [
          jsx('span', { className: 'text-[10px] text-(--ui-text-tertiary) mb-1', children: S.spectrum }),
          jsx(SpectrumPlot, {
            dbfs: spec.dbfs,
            centerHz: spec.centerHz || 0,
            sampleRateHz: spec.sampleRateHz || 0,
          }),
        ],
      }),

      // Steuerung
      jsxs('div', {
        className: 'flex items-center gap-2 mb-1',
        children: [
          jsx('button', {
            onClick: handleStart,
            disabled: st.running,
            className: 'flex-1 px-2 py-1 text-[10px] rounded bg-(--chrome-action-hover) hover:bg-(--ui-success) text-(--ui-success-foreground) disabled:opacity-50',
            children: S.start,
          }),
          jsx('button', {
            onClick: handleStop,
            disabled: !st.running,
            className: 'flex-1 px-2 py-1 text-[10px] rounded bg-(--chrome-action-hover) hover:bg-(--ui-destructive) text-(--ui-destructive-foreground) disabled:opacity-50',
            children: S.stop,
          }),
        ],
      }),

      jsxs('div', {
        className: 'flex items-center gap-2 mb-1',
        children: [
          jsx('input', {
            placeholder: 'z. B. fm / 7',
            value: modeInput,
            onChange: (e) => setModeInput(e.target.value),
            className: 'flex-1 px-1.5 py-px rounded border border-(--ui-stroke-secondary) text-[10px] bg-(--chrome-action-bg)',
          }),
          jsx('button', {
            onClick: handleSetMode,
            className: 'px-2 py-1 text-[10px] rounded bg-(--chrome-action-hover) hover:bg-(--ui-primary) text-(--ui-primary-foreground)',
            children: S.setMode,
          }),
        ],
      }),

      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('input', {
            placeholder: 'z. B. 100M / 100000000',
            value: freqInput,
            onChange: (e) => setFreqInput(e.target.value),
            className: 'flex-1 px-1.5 py-px rounded border border-(--ui-stroke-secondary) text-[10px] bg-(--chrome-action-bg)',
          }),
          jsx('button', {
            onClick: handleSetFreq,
            className: 'px-2 py-1 text-[10px] rounded bg-(--chrome-action-hover) hover:bg-(--ui-primary) text-(--ui-primary-foreground)',
            children: S.setFreq,
          }),
        ],
      }),

      msg && jsx('div', {
        className: 'text-[10px] text-(--ui-text-secondary) mt-1',
        children: msg,
      }),

      // Geräte / Modi zählen
      jsx('div', {
        className: 'text-[9px] text-(--ui-text-muted) mt-2',
        children: `${devices.length} ${S.device} · ${modes.length} ${S.mode}`,
      }),
    ],
  })
}

// ---------- Export ----------

export default {
  id: ID,
  name: 'onair4hermes',
  register(ctx) {
    ctx.i18n.register({
      en: {
        title: 'onair4hermes',
        paneTitle: 'OnAir (SDR)',
        status: 'Status',
        running: 'Running',
        stopped: 'Stopped',
        offline: 'OnAir API not reachable',
        device: 'Device',
        mode: 'Mode',
        frequency: 'Frequency',
        sampleRate: 'Sample Rate',
        gain: 'Gain',
        snr: 'SNR',
        quality: 'Quality',
        locked: 'Locked',
        unlocked: 'Unlocked',
        start: '▶ Start',
        stop: '⏹ Stop',
        setMode: 'Set mode',
        setFreq: 'Set frequency',
        hz: 'Hz',
        mhz: 'MHz',
        spectrum: 'Spectrum',
        bins: 'Bins',
        noDevices: 'No devices',
        noModes: 'No modes',
        chipTooltip: 'OnAir SDR Receiver',
        errorFetch: 'Error fetching OnAir API',
      },
      de: {
        title: 'onair4hermes',
        paneTitle: 'OnAir (SDR)',
        status: 'Status',
        running: 'Läuft',
        stopped: 'Gestoppt',
        offline: 'OnAir API nicht erreichbar',
        device: 'Gerät',
        mode: 'Modus',
        frequency: 'Frequenz',
        sampleRate: 'Sample Rate',
        gain: 'Gain',
        snr: 'SNR',
        quality: 'Qualität',
        locked: 'Gelockt',
        unlocked: 'Nicht gelockt',
        start: '▶ Start',
        stop: '⏹ Stop',
        setMode: 'Modus setzen',
        setFreq: 'Frequenz setzen',
        hz: 'Hz',
        mhz: 'MHz',
        spectrum: 'Spektrum',
        bins: 'Bins',
        noDevices: 'Keine Geräte',
        noModes: 'Keine Modi',
        chipTooltip: 'OnAir SDR Empfänger',
        errorFetch: 'Fehler beim Abruf der OnAir API',
      },
    })

    ctx.register({
      id: 'onair-pane',
      area: 'panes',
      title: 'onair4hermes',
      data: { placement: 'right', width: '350px' },
      render: () => jsx(OnAirPane, {}),
    })

    ctx.register({
      id: 'onair-chip',
      area: 'statusBar.right',
      order: 110,
      render: () => jsx(StatusChip, {}),
    })
  },
}
