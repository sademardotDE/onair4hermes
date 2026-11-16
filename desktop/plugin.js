/**
 * onair4hermes — Hermes Desktop Plugin für OnAir (SDR / Funküberwachung).
 *
 * Save as: <hermes home>/desktop-plugins/onair4hermes/plugin.js
 * Reload: ⌘K / Ctrl+K → "Reload desktop plugins"
 *
 * Alle Aufrufe laufen über das Dashboard-Backend dieses Plugins
 * (ctx.rest → /api/plugins/onair4hermes/...). Ein direktes fetch zur
 * OnAir-API scheitert am fehlenden CORS-Header im Electron-Renderer;
 * der Proxy kennt außerdem den API-Token aus den Plugin-Settings.
 */

import { Tip, usePluginI18n } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'onair4hermes'

function strings(locale) {
  return locale.startsWith('de')
    ? {
        title: 'OnAir (SDR)',
        running: 'Läuft',
        stopped: 'Gestoppt',
        offline: 'OnAir nicht erreichbar',
        device: 'Gerät',
        mode: 'Modus',
        frequency: 'Frequenz',
        snr: 'SNR',
        quality: 'Qualität',
        locked: 'Gelockt',
        unlocked: 'Nicht gelockt',
        start: '▶ Start',
        stop: '⏹ Stop',
        spectrum: 'Spektrum',
        mhz: 'MHz',
        hz: 'Hz',
        startHint: 'z. B. fm / 7',
        freqHint: 'z. B. 100M / 100000000',
        setMode: 'Modus setzen',
        setFreq: 'Frequenz setzen',
        started: 'Receiver gestartet',
        stoppedMsg: 'Receiver gestoppt',
        modeSet: 'Modus gesetzt',
        freqSet: 'Frequenz gesetzt',
        noDevices: 'Kein Gerät gemeldet',
        tokenMissing: 'Token fehlt (Plugin-Einstellungen)',
      }
    : {
        title: 'OnAir (SDR)',
        running: 'Running',
        stopped: 'Stopped',
        offline: 'OnAir not reachable',
        device: 'Device',
        mode: 'Mode',
        frequency: 'Frequency',
        snr: 'SNR',
        quality: 'Quality',
        locked: 'Locked',
        unlocked: 'Unlocked',
        start: '▶ Start',
        stop: '⏹ Stop',
        spectrum: 'Spectrum',
        mhz: 'MHz',
        hz: 'Hz',
        startHint: 'e.g. fm / 7',
        freqHint: 'e.g. 100M / 100000000',
        setMode: 'Set mode',
        setFreq: 'Set frequency',
        started: 'Receiver started',
        stoppedMsg: 'Receiver stopped',
        modeSet: 'Mode set',
        freqSet: 'Frequency set',
        noDevices: 'No device reported',
        tokenMissing: 'Token missing (plugin settings)',
      }
}

function getLocale() {
  try {
    const lang = typeof document !== 'undefined' ? document.documentElement.lang : ''
    if (typeof lang === 'string') {
      if (lang.startsWith('de')) return 'de'
      if (lang.startsWith('en')) return 'en'
    }
  } catch {}
  return 'en'
}

function errText(err) {
  if (!err) return ''
  if (typeof err.message === 'string' && err.message) return err.message
  if (typeof err.detail === 'string') return err.detail
  if (err.detail && typeof err.detail.error === 'string') return err.detail.error
  return String(err)
}

async function call(rest, path, opts) {
  return rest(path, opts)
}

function StatusDot({ running, tooltip, label }) {
  return jsx(Tip, {
    label: tooltip,
    children: jsx('button', {
      type: 'button',
      className:
        'inline-flex h-full items-center gap-1 px-2 text-[0.6875rem] transition-colors' +
        ' text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
      children: running ? '● OnAir' : '○ OnAir',
      title: label,
    }),
  })
}

function StatusChip({ rest }) {
  const t = usePluginI18n(ID)
  const S = strings(getLocale())
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const st = await call(rest, '/status')
        if (!cancelled) setRunning(Boolean(st && st.onair && st.onair.running))
      } catch {
        if (!cancelled) setRunning(false)
      }
    }
    tick()
    const timer = setInterval(tick, 5000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [rest])

  return jsx(StatusDot, {
    running,
    tooltip: t('chipTooltip'),
    label: running ? S.running : S.stopped,
  })
}

function SpectrumPlot({ dbfs, centerHz }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !Array.isArray(dbfs) || dbfs.length === 0) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = Math.max(1, Math.floor(rect.width * dpr))
    canvas.height = Math.max(1, Math.floor(rect.height * dpr))
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const w = rect.width
    const h = rect.height
    const dark =
      typeof document !== 'undefined' &&
      document.documentElement.classList.contains('dark')
    ctx.fillStyle = dark ? '#1e1e22' : '#ffffff'
    ctx.fillRect(0, 0, w, h)

    const minDb = -100
    const maxDb = -20
    const barW = Math.max(1, w / dbfs.length)
    for (let i = 0; i < dbfs.length; i++) {
      const db = Number(dbfs[i])
      const pct = Math.max(0, Math.min(1, (db - minDb) / (maxDb - minDb)))
      const barH = h * pct
      ctx.fillStyle = db > -40 ? '#f85149' : db > -60 ? '#d29922' : '#58a6ff'
      ctx.fillRect(i * barW, h - barH, Math.max(1, barW - 1), barH)
    }

    ctx.fillStyle = dark ? '#c9d1d9' : '#1c2128'
    ctx.font = '10px ui-monospace, monospace'
    ctx.fillText(`${(Number(centerHz || 0) / 1e6).toFixed(3)} MHz`, 4, h - 4)
  }, [dbfs, centerHz])

  return jsx('canvas', {
    ref: canvasRef,
    style: { width: '100%', height: '110px', borderRadius: '4px', background: 'transparent' },
  })
}

function Row({ label, children }) {
  return jsxs('div', {
    className: 'flex items-center gap-2 text-[11px]',
    children: [
      jsx('span', { className: 'w-16 shrink-0 text-(--ui-text-secondary)', children: label }),
      jsx('span', { className: 'min-w-0 truncate text-(--ui-text-primary)', children }),
    ],
  })
}

function OnAirPane({ rest }) {
  const S = strings(getLocale())
  const [status, setStatus] = useState(null)
  const [devices, setDevices] = useState([])
  const [modes, setModes] = useState([])
  const [telemetry, setTelemetry] = useState(null)
  const [spectrum, setSpectrum] = useState(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState('')
  const [modeInput, setModeInput] = useState('')
  const [freqInput, setFreqInput] = useState('')
  const [message, setMessage] = useState('')

  const flash = (text) => {
    setMessage(text)
    setTimeout(() => setMessage(''), 2500)
  }

  const refresh = async () => {
    try {
      const st = await call(rest, '/status')
      setStatus(st)
      setOffline(!(st && st.onair && st.onair.running !== undefined))
      const [dev, mods, tel, spec] = await Promise.all([
        call(rest, '/devices').catch(() => null),
        call(rest, '/modes').catch(() => null),
        call(rest, '/telemetry').catch(() => null),
        call(rest, '/spectrum?bins=96').catch(() => null),
      ])
      setDevices((dev && dev.devices) || [])
      setModes((mods && mods.modes) || [])
      setTelemetry((tel && tel.telemetry) || null)
      setSpectrum((spec && spec.spectrum) || null)
      setError('')
    } catch (err) {
      setOffline(true)
      setError(errText(err))
    }
  }

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      if (!cancelled) await refresh()
    }
    tick()
    const timer = setInterval(tick, 3000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rest])

  const post = async (path, body, okMessage) => {
    try {
      await call(rest, path, { method: 'POST', body: body || {} })
      flash(okMessage)
      await refresh()
    } catch (err) {
      flash(`${S.offline}: ${errText(err)}`)
    }
  }

  const handleSetMode = () => {
    const value = modeInput.trim()
    if (!value) return
    const numeric = Number(value)
    post('/mode', { family: Number.isNaN(numeric) ? value : numeric }, S.modeSet)
  }

  const handleSetFreq = () => {
    const value = freqInput.trim()
    if (!value) return
    if (value.toLowerCase().endsWith('m')) {
      post('/frequency', { mhz: parseFloat(value.slice(0, -1)) }, S.freqSet)
    } else {
      post('/frequency', { hz: parseInt(value, 10) }, S.freqSet)
    }
  }

  const onair = (status && status.onair) || {}
  const tel = telemetry || {}
  const details = tel.details || {}
  const spec = spectrum || {}
  const running = Boolean(onair.running)
  const frequencyHz = onair.frequencyHz

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 overflow-auto p-3 text-sm',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between',
        children: [
          jsx('div', { className: 'font-medium', children: S.title }),
          jsx('span', {
            className:
              'inline-flex items-center gap-1 rounded px-1.5 py-px text-[10px] font-mono' +
              (offline
                ? ' bg-(--chrome-action-hover) text-(--ui-text-tertiary)'
                : running
                  ? ' bg-(--ui-success)/20 text-(--ui-success)'
                  : ' bg-(--chrome-action-hover) text-(--ui-text-tertiary)'),
            children: offline ? S.offline : running ? S.running : S.stopped,
          }),
        ],
      }),

      jsxs('div', {
        className: 'rounded border border-(--ui-stroke-secondary) p-2 flex flex-col gap-1',
        children: [
          jsx(Row, { label: S.device, children: onair.device || S.noDevices }),
          jsx(Row, { label: S.mode, children: onair.mode || '—' }),
          frequencyHz != null
            ? jsx(Row, {
                label: S.frequency,
                children: `${(frequencyHz / 1e6).toFixed(3)} ${S.mhz}`,
              })
            : null,
          jsx(Row, {
            label: S.snr,
            children:
              tel.snrDb != null
                ? `${Number(tel.snrDb).toFixed(1)} dB${details.snrKind ? ` (${details.snrKind})` : ''}`
                : '—',
          }),
          jsx(Row, {
            label: S.quality,
            children:
              tel.quality && tel.quality.percent != null
                ? `${tel.quality.percent}%${tel.quality.label ? ` · ${tel.quality.label}` : ''}`
                : '—',
          }),
          tel.locked != null
            ? jsx('div', {
                className:
                  'mt-1 inline-flex w-fit items-center rounded px-1.5 py-px text-[10px]' +
                  (tel.locked
                    ? ' bg-(--ui-success)/20 text-(--ui-success)'
                    : ' bg-(--chrome-action-hover) text-(--ui-text-tertiary)'),
                children: tel.locked ? S.locked : S.unlocked,
              })
            : null,
          details.psName
            ? jsx('div', {
                className: 'text-[10px] text-(--ui-text-secondary)',
                children: `${details.psName}${details.radioText ? ' — ' + details.radioText : ''}`,
              })
            : null,
        ],
      }),

      spec.dbfs && spec.dbfs.length
        ? jsxs('div', {
            className: 'flex flex-col gap-1',
            children: [
              jsx('span', { className: 'text-[10px] text-(--ui-text-tertiary)', children: S.spectrum }),
              jsx(SpectrumPlot, { dbfs: spec.dbfs, centerHz: spec.centerHz || 0 }),
            ],
          })
        : null,

      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('button', {
            type: 'button',
            onClick: () => post('/start', {}, S.started),
            disabled: offline || running,
            className:
              'flex-1 rounded bg-(--chrome-action-hover) px-2 py-1 text-[10px] hover:bg-(--ui-success) disabled:opacity-50',
            children: S.start,
          }),
          jsx('button', {
            type: 'button',
            onClick: () => post('/stop', {}, S.stoppedMsg),
            disabled: offline || !running,
            className:
              'flex-1 rounded bg-(--chrome-action-hover) px-2 py-1 text-[10px] hover:bg-(--ui-destructive) disabled:opacity-50',
            children: S.stop,
          }),
        ],
      }),

      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('input', {
            value: modeInput,
            onChange: (e) => setModeInput(e.target.value),
            onKeyDown: (e) => {
              if (e.key === 'Enter') handleSetMode()
            },
            placeholder: S.startHint,
            className:
              'min-w-0 flex-1 rounded border border-(--ui-stroke-secondary) bg-(--chrome-action-bg) px-1.5 py-px text-[10px]',
          }),
          jsx('button', {
            type: 'button',
            onClick: handleSetMode,
            disabled: offline,
            className:
              'rounded bg-(--chrome-action-hover) px-2 py-1 text-[10px] hover:bg-(--ui-primary) disabled:opacity-50',
            children: S.setMode,
          }),
        ],
      }),

      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('input', {
            value: freqInput,
            onChange: (e) => setFreqInput(e.target.value),
            onKeyDown: (e) => {
              if (e.key === 'Enter') handleSetFreq()
            },
            placeholder: S.freqHint,
            className:
              'min-w-0 flex-1 rounded border border-(--ui-stroke-secondary) bg-(--chrome-action-bg) px-1.5 py-px text-[10px]',
          }),
          jsx('button', {
            type: 'button',
            onClick: handleSetFreq,
            disabled: offline,
            className:
              'rounded bg-(--chrome-action-hover) px-2 py-1 text-[10px] hover:bg-(--ui-primary) disabled:opacity-50',
            children: S.setFreq,
          }),
        ],
      }),

      message || error
        ? jsx('div', {
            className: 'text-[10px] text-(--ui-text-secondary)',
            children: message || error,
          })
        : null,

      jsx('div', {
        className: 'text-[9px] text-(--ui-text-muted)',
        children: `${devices.length} ${S.device} · ${modes.length} ${S.mode}`,
      }),
    ],
  })
}

export default {
  id: ID,
  name: 'OnAir (SDR)',
  register(ctx) {
    const rest = (path, opts) => ctx.rest(path, opts)
    ctx.i18n.register({
      en: { chipTooltip: 'OnAir SDR receiver' },
      de: { chipTooltip: 'OnAir SDR-Empfänger' },
    })
    ctx.registerMany([
      {
        id: 'pane',
        area: 'panes',
        title: 'OnAir (SDR)',
        data: { placement: 'right', width: '360px' },
        render: () => jsx(OnAirPane, { rest }),
      },
      {
        id: 'chip',
        area: 'statusBar.right',
        order: 110,
        render: () => jsx(StatusChip, { rest }),
      },
    ])
  },
}
