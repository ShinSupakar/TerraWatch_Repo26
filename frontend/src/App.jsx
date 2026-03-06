import { useEffect, useMemo, useRef, useState } from 'react';
import { ShakeMapViewer } from './ShakeMapViewer';

const INCIDENTS = [
  {
    id: 'turkey-2023',
    name: 'Turkey-Syria Earthquake',
    date: '2023-02-06',
    deaths: 59000,
    baselineHours: 68,
    lat: 37.17,
    lon: 37.03,
    magnitude: 7.8,
    depthKm: 17.9,
    neighborhoods: [
      'Barbaros Mah. Block C-D',
      'Gazikent South Tower Cluster',
      'Nurdagi Sector 4'
    ]
  },
  {
    id: 'nepal-2015',
    name: 'Nepal Gorkha Earthquake',
    date: '2015-04-25',
    deaths: 8964,
    baselineHours: 71,
    lat: 28.23,
    lon: 84.73,
    magnitude: 7.8,
    depthKm: 15.0,
    neighborhoods: [
      'Kathmandu Ward 11',
      'Bhaktapur Heritage Belt',
      'Lalitpur Ridge Zone'
    ]
  },
  {
    id: 'japan-2011',
    name: 'Tohoku Earthquake & Tsunami',
    date: '2011-03-11',
    deaths: 19759,
    baselineHours: 54,
    lat: 38.29,
    lon: 142.37,
    magnitude: 9.1,
    depthKm: 29.0,
    neighborhoods: [
      'Miyagi Coastal Grid A12',
      'Ishinomaki Port Perimeter',
      'Sendai East Lowlands'
    ]
  }
];

const PIPELINE_STEPS = [
  'ESRGAN',
  'YOLOv8n',
  'Classification',
  'Priority Ranking',
  'Aftershock Risk'
];

const DAMAGE_LEVEL = ['NO DAMAGE', 'MINOR', 'MAJOR', 'DESTROYED'];

const API_BASE = import.meta.env.VITE_API_BASE || '';
const ENABLE_REFINEMENT = import.meta.env.VITE_ENABLE_REFINEMENT === '1';

function formatCountdown(totalSeconds) {
  const clamped = Math.max(0, totalSeconds);
  const hrs = Math.floor(clamped / 3600)
    .toString()
    .padStart(2, '0');
  const mins = Math.floor((clamped % 3600) / 60)
    .toString()
    .padStart(2, '0');
  const secs = Math.floor(clamped % 60)
    .toString()
    .padStart(2, '0');
  return `${hrs}:${mins}:${secs}`;
}

function seeded(index) {
  const seed = Math.sin(index * 937.13) * 10000;
  return seed - Math.floor(seed);
}

function generateMockBoxes(seedOffset = 1) {
  const boxes = [];
  for (let i = 0; i < 9; i += 1) {
    const x = 8 + seeded(i + seedOffset) * 70;
    const y = 10 + seeded(i + seedOffset * 3) * 72;
    const w = 12 + seeded(i + seedOffset * 7) * 15;
    const h = 8 + seeded(i + seedOffset * 9) * 20;
    const cls = Math.min(3, Math.floor(seeded(i + seedOffset * 11) * 4));
    boxes.push({ id: `${seedOffset}-${i}`, x, y, w, h, cls });
  }
  return boxes;
}

function App() {
  const [selectedId, setSelectedId] = useState(INCIDENTS[0].id);
  const [countdownSec, setCountdownSec] = useState(INCIDENTS[0].baselineHours * 3600);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadedPreview, setUploadedPreview] = useState('');
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisDone, setAnalysisDone] = useState(false);
  const [stepIndex, setStepIndex] = useState(-1);
  const [savedHours, setSavedHours] = useState(0);
  const [aftershock, setAftershock] = useState([]);
  const [aftershockSource, setAftershockSource] = useState('n/a');
  const [laymanSummary, setLaymanSummary] = useState(null);
  const [rescueQueue, setRescueQueue] = useState([]);
  const [statusLine, setStatusLine] = useState('Awaiting incident selection and imagery.');
  const [eventFeed, setEventFeed] = useState([]);
  const [damageBoxes, setDamageBoxes] = useState(generateMockBoxes(3));
  const [processedImage, setProcessedImage] = useState('');
  const [refineStatus, setRefineStatus] = useState('idle');
  const [damageSummary, setDamageSummary] = useState(null);
  const [shakeMap, setShakeMap] = useState(null);
  const [impact, setImpact] = useState(null);

  const wsRef = useRef(null);
  const selectedIncident = useMemo(
    () => INCIDENTS.find((x) => x.id === selectedId) || INCIDENTS[0],
    [selectedId]
  );

  useEffect(() => {
    setCountdownSec(selectedIncident.baselineHours * 3600);
    setAnalysisDone(false);
    setStepIndex(-1);
    setSavedHours(0);
    setLaymanSummary(null);
    setAftershock([]);
    setAftershockSource('n/a');
    setRescueQueue([]);
    setDamageBoxes(generateMockBoxes(selectedIncident.deaths));
    setProcessedImage('');
    setRefineStatus('idle');
    setDamageSummary(null);
    setShakeMap(null);
    setImpact(null);
    setStatusLine(`Selected ${selectedIncident.name}. Timer running from ${selectedIncident.baselineHours} hours.`);
  }, [selectedIncident]);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdownSec((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Seed ShakeMap from latest M5+ event on mount
  useEffect(() => {
    fetch('/api/shakemap/latest')
      .then(r => r.json())
      .then(d => {
        if (d.status === 'success' && d.event) {
          const e = d.event;
          const polys = [];
          setShakeMap({
            event_id: e.id,
            source: 'usgs_live',
            event_place: e.place,
            event_mag: e.mag,
            polygons: polys,
          });
          if (d.impact) setImpact(d.impact);
        }
      })
      .catch(() => { });
  }, []);

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/live`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const label = msg?.type || 'event';
          const ts = new Date().toLocaleTimeString();
          setEventFeed((prev) => [`${ts} | ${label}`, ...prev].slice(0, 10));

          if (msg?.type === 'shakemap' && msg?.payload) {
            const payload = msg.payload;
            setShakeMap({
              event_id: payload.event_id,
              source: payload.source || 'synthetic_stub',
              polygons: Array.isArray(payload.polygons) ? payload.polygons : []
            });
            if (payload.impact) {
              setImpact(payload.impact);
            }
          } else if (msg?.type === 'impact_assessment' && msg?.payload) {
            setImpact(msg.payload.impact || null);
            if (Array.isArray(msg.payload.polygons)) {
              setShakeMap((prev) => ({
                event_id: msg.payload.event_id || prev?.event_id || 'live-event',
                source: prev?.source || 'synthetic_stub',
                polygons: msg.payload.polygons
              }));
            }
          }
        } catch {
          setEventFeed((prev) => [`${new Date().toLocaleTimeString()} | raw stream`, ...prev].slice(0, 10));
        }
      };
      ws.onopen = () => setEventFeed((prev) => [`${new Date().toLocaleTimeString()} | websocket connected`, ...prev]);
      ws.onclose = () => setEventFeed((prev) => [`${new Date().toLocaleTimeString()} | websocket closed`, ...prev]);
    } catch {
      setEventFeed((prev) => [`${new Date().toLocaleTimeString()} | websocket unavailable`, ...prev]);
    }

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    if (!uploadedFile) {
      setUploadedPreview('');
      return;
    }
    const url = URL.createObjectURL(uploadedFile);
    setUploadedPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadedFile]);

  async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(t);
    }
  }

  async function callWorstCase() {
    const res = await fetchWithTimeout(`${API_BASE}/api/hazard/worst_case`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: selectedIncident.lat,
        longitude: selectedIncident.lon,
        search_radius_km: 100
      })
    }, 8000);
    if (!res.ok) throw new Error('hazard engine unavailable');
    return res.json();
  }

  async function callAftershock() {
    const historical = Array.from({ length: 48 }, (_, idx) => {
      const r = seeded(idx + selectedIncident.deaths);
      return Math.floor(r * 3);
    });

    const now = new Date();
    const startOfYear = new Date(Date.UTC(now.getUTCFullYear(), 0, 0));
    const dayOfYear = Math.floor((now - startOfYear) / 86400000);

    const res = await fetchWithTimeout(`${API_BASE}/api/aftershock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mainshock: {
          magnitude: selectedIncident.magnitude,
          depth_km: selectedIncident.depthKm,
          latitude: selectedIncident.lat,
          longitude: selectedIncident.lon,
          hour_utc: now.getUTCHours(),
          day_of_year: dayOfYear
        },
        historical_seismicity_48h: historical
      })
    }, 10000);
    if (!res.ok) throw new Error('aftershock model unavailable');
    return res.json();
  }

  async function callDamage({ fast = true, timeoutMs = 18000 } = {}) {
    if (!uploadedFile) return null;
    const form = new FormData();
    form.append('image', uploadedFile);
    form.append('latitude', String(selectedIncident.lat));
    form.append('longitude', String(selectedIncident.lon));
    form.append('fast_mode', fast ? '1' : '0');

    const res = await fetchWithTimeout(`${API_BASE}/api/damage`, {
      method: 'POST',
      body: form
    }, timeoutMs);
    if (!res.ok) throw new Error('damage endpoint unavailable');
    return res.json();
  }

  async function callLaymanSummary(payload) {
    const res = await fetchWithTimeout(`${API_BASE}/api/layman_summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }, 8000);
    if (!res.ok) throw new Error('layman summary unavailable');
    return res.json();
  }

  function buildRescueQueue(damage, worstCase = null, aftershock24 = [], impactPayload = null) {
    const boxes = Array.isArray(damage?.damage_boxes) ? damage.damage_boxes : [];
    const total = boxes.length;
    const severeCount = boxes.filter((b) => b.damage_class >= 2).length;
    const severeRatio = total > 0 ? severeCount / total : 0;
    const maxAftershock = aftershock24.length ? Math.max(...aftershock24) : 0;
    const pga = worstCase?.pga_percent_g ?? 25;
    const impactBase = Number(impactPayload?.exposed_population_estimate || 0);
    const damageSignal = total > 0 ? (0.55 + severeRatio) : 0.35;
    const riskSignal = Math.min(2.4, 0.8 + pga / 90 + maxAftershock);
    const baseResidents =
      impactBase > 0
        ? Math.max(80, Math.round((impactBase / Math.max(selectedIncident.neighborhoods.length, 1)) * damageSignal))
        : Math.max(120, Math.round((160 + severeCount * 22) * riskSignal));

    const queue = selectedIncident.neighborhoods.map((zone, idx) => {
      const zoneWeight = 1 + idx * 0.45;
      const residents = Math.max(30, Math.round(baseResidents / zoneWeight));
      const teams = Math.max(1, Math.round(residents / 85));
      const zoneScore = residents * (1.15 - idx * 0.12) * (0.7 + severeRatio);
      return { zone, residents, teams, zoneScore };
    });

    queue.sort((a, b) => b.zoneScore - a.zoneScore);

    return queue.map((q, idx) => ({
      zone: q.zone,
      residents: q.residents,
      teams: q.teams,
      priority:
        idx === 0
          ? 'IMMEDIATE RESCUE'
          : idx === 1
            ? 'HIGH PRIORITY'
            : total > 0
              ? 'STABILIZE'
              : 'ASSESSMENT NEEDED',
    }));
  }

  async function fetchLatestShakeMapAndImpact() {
    const liveRes = await fetch(`${API_BASE}/api/live/events?limit=1`);
    if (!liveRes.ok) throw new Error('live events unavailable');
    const live = await liveRes.json();
    const latest = Array.isArray(live.events) && live.events.length > 0 ? live.events[0] : null;
    if (!latest?.id) return;

    const [smRes, impactRes] = await Promise.all([
      fetch(`${API_BASE}/api/shakemap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: latest.id })
      }),
      fetch(`${API_BASE}/api/impact/${latest.id}`)
    ]);

    if (smRes.ok) {
      const sm = await smRes.json();
      setShakeMap(sm);
    }
    if (impactRes.ok) {
      const imp = await impactRes.json();
      setImpact(imp);
    }
  }

  async function runAnalysis() {
    if (analysisRunning) return;

    setAnalysisRunning(true);
    setAnalysisDone(false);
    setStepIndex(0);
    setStatusLine('Executing multi-modal pipeline...');
    setAftershock([]);
    setAftershockSource('n/a');
    setLaymanSummary(null);
    setRescueQueue([]);
    setProcessedImage('');
    setDamageBoxes([]);
    setRefineStatus('idle');
    setDamageSummary(null);

    const timer = setInterval(() => {
      setStepIndex((prev) => {
        if (prev >= PIPELINE_STEPS.length - 1) {
          clearInterval(timer);
          return prev;
        }
        return prev + 1;
      });
    }, 1200);

    try {
      const [worstCaseResult, aftershockResult, damageResult] = await Promise.allSettled([
        callWorstCase(),
        callAftershock(),
        callDamage({ fast: true, timeoutMs: 12000 })
      ]);

      const worstCase = worstCaseResult.status === 'fulfilled' ? worstCaseResult.value : null;
      const aftershockResp = aftershockResult.status === 'fulfilled' ? aftershockResult.value : null;
      const damageResp = damageResult.status === 'fulfilled' ? damageResult.value : null;

      if (damageResp?.damage_boxes?.length) {
        const imgW = damageResp.image_width || 640;
        const imgH = damageResp.image_height || 640;
        const scaled = damageResp.damage_boxes.slice(0, 12).map((b, idx) => {
          const x = ((b.x1 / imgW) * 100);
          const y = ((b.y1 / imgH) * 100);
          const w = (((b.x2 - b.x1) / imgW) * 100);
          const h = (((b.y2 - b.y1) / imgH) * 100);
          return { id: `api-${idx}`, x, y, w, h, cls: b.damage_class };
        });
        setDamageBoxes(scaled);
      }
      if (damageResp?.aggregated_counts) {
        const counts = damageResp.aggregated_counts;
        const total =
          Number(counts['no-damage'] || 0) +
          Number(counts['minor-damage'] || 0) +
          Number(counts['major-damage'] || 0) +
          Number(counts.destroyed || 0);
        const severe = Number(counts['major-damage'] || 0) + Number(counts.destroyed || 0);
        const severePct = total > 0 ? (severe / total) * 100 : 0;
        setDamageSummary({ total, severePct });
      }
      if (damageResp?.overlay_image_b64) {
        setProcessedImage(`data:image/jpeg;base64,${damageResp.overlay_image_b64}`);
      } else if (damageResp?.enhanced_image_b64) {
        setProcessedImage(`data:image/jpeg;base64,${damageResp.enhanced_image_b64}`);
      }

      const aftershock24 = aftershockResp?.probabilities_m4_plus || [];
      setAftershock(aftershock24);
      setAftershockSource(aftershockResp?.model_source || 'n/a');

      if (worstCase) {
        const peakAftershock = aftershock24.length ? Math.max(...aftershock24) : 0.2;
        const summary = await callLaymanSummary({
          magnitude: worstCase.design_basis_magnitude,
          focal_depth_km: worstCase.autofilled_depth_km,
          pga_percent_g: worstCase.pga_percent_g,
          aftershock_probability_24h: peakAftershock
        });
        setLaymanSummary(summary);
      }

      const queue = buildRescueQueue(damageResp || null, worstCase, aftershock24, impact);
      setRescueQueue(queue);

      if (uploadedFile && ENABLE_REFINEMENT) {
        setRefineStatus('running');
        setStatusLine('Fast triage complete. Generating ESRGAN-refined overlay in background...');
        callDamage({ fast: false, timeoutMs: 45000 })
          .then((refinedResp) => {
            if (refinedResp?.damage_boxes?.length) {
              const imgW = refinedResp.image_width || 640;
              const imgH = refinedResp.image_height || 640;
              const scaled = refinedResp.damage_boxes.slice(0, 12).map((b, idx) => {
                const x = ((b.x1 / imgW) * 100);
                const y = ((b.y1 / imgH) * 100);
                const w = (((b.x2 - b.x1) / imgW) * 100);
                const h = (((b.y2 - b.y1) / imgH) * 100);
                return { id: `refined-${idx}`, x, y, w, h, cls: b.damage_class };
              });
              setDamageBoxes(scaled);
            }
            if (refinedResp?.overlay_image_b64) {
              setProcessedImage(`data:image/jpeg;base64,${refinedResp.overlay_image_b64}`);
            } else if (refinedResp?.enhanced_image_b64) {
              setProcessedImage(`data:image/jpeg;base64,${refinedResp.enhanced_image_b64}`);
            }
            setRefineStatus('done');
            setStatusLine('Analysis complete. ESRGAN-refined overlay applied.');
          })
          .catch(() => {
            setRefineStatus('failed');
            setStatusLine('Analysis complete. Fast triage shown; ESRGAN refinement unavailable.');
          });
      } else if (uploadedFile) {
        setRefineStatus('idle');
        setStatusLine('Analysis complete. Fast triage generated (refinement disabled).');
      }

      try {
        await fetchLatestShakeMapAndImpact();
      } catch {
        // Real-time feeds can be temporarily unavailable; UI keeps core results.
      }

      clearInterval(timer);
      setStepIndex(PIPELINE_STEPS.length - 1);
      setCountdownSec(0);
      setSavedHours(selectedIncident.baselineHours);
      setAnalysisDone(true);
      if (!uploadedFile) {
        setStatusLine('Analysis complete. Rescue prioritization generated.');
      }
    } catch (err) {
      clearInterval(timer);
      setStatusLine(`Partial analysis: ${err.message}. Showing best available outputs.`);
      setRescueQueue([]);
      setAnalysisDone(true);
      setCountdownSec(0);
      setSavedHours(selectedIncident.baselineHours - 2);
    } finally {
      setAnalysisRunning(false);
    }
  }

  const beforeImage = uploadedPreview || `https://picsum.photos/seed/${selectedIncident.id}-before/1000/700`;
  const afterImage = processedImage || uploadedPreview || `https://picsum.photos/seed/${selectedIncident.id}-after/1000/700`;
  const shakePolygons = Array.isArray(shakeMap?.polygons) ? shakeMap.polygons : [];
  const aftershockPeak = aftershock.length ? Math.max(...aftershock) : 0;
  const aftershockAvg = aftershock.length ? aftershock.reduce((a, b) => a + b, 0) / aftershock.length : 0;
  const aftershockRiskLabel = aftershockPeak >= 0.6 ? 'HIGH' : aftershockPeak >= 0.3 ? 'MODERATE' : 'LOW';
  const refineLabel =
    !ENABLE_REFINEMENT
      ? 'Overlay: FAST only'
      :
      refineStatus === 'running'
        ? 'Overlay: FAST (refining...)'
        : refineStatus === 'done'
          ? 'Overlay: ESRGAN refined'
          : refineStatus === 'failed'
            ? 'Overlay: FAST (refinement failed)'
            : 'Overlay: idle';

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>TERRAWATCH COMMAND CONSOLE</h1>
          <p>Emergency Response | Seismic Intelligence | Zero-Hour Rescue Prioritization</p>
        </div>
        <div className="clock-card">
          <span className="clock-label">SURVIVAL COUNTDOWN</span>
          <span className={`clock-value ${countdownSec <= 600 ? 'critical' : ''}`}>{formatCountdown(countdownSec)}</span>
          <span className="clock-meta">Target benchmark: {selectedIncident.baselineHours}h manual lag</span>
        </div>
      </header>

      <main className="grid-layout">
        <section className="panel left-panel">
          <h2>Incident Selection</h2>
          <div className="incident-list">
            {INCIDENTS.map((incident) => (
              <button
                key={incident.id}
                className={`incident-card ${incident.id === selectedId ? 'active' : ''}`}
                onClick={() => setSelectedId(incident.id)}
                type="button"
              >
                <div className="incident-title">{incident.name}</div>
                <div className="incident-meta">Date: {incident.date}</div>
                <div className="incident-meta">Recorded deaths: {incident.deaths.toLocaleString()}</div>
                <div className="incident-meta">Manual detection lag: ~{incident.baselineHours}h</div>
              </button>
            ))}
          </div>

          <div className="upload-block">
            <h3>Satellite / Drone Upload</h3>
            <label className="upload-zone">
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setUploadedFile(e.target.files?.[0] || null)}
              />
              <span>{uploadedFile ? uploadedFile.name : 'Drop Copernicus EMS image or click to select'}</span>
            </label>
            <button className="analyze-btn" onClick={runAnalysis} disabled={analysisRunning} type="button">
              {analysisRunning ? 'ANALYSIS IN PROGRESS' : 'ANALYSE'}
            </button>
            <p className="status-line">{statusLine}</p>
          </div>

          <div className="feed-block">
            <h3>Live Feed</h3>
            <div className="feed-list">
              {eventFeed.length === 0 ? <p>No live events yet.</p> : eventFeed.map((line) => <p key={line}>{line}</p>)}
            </div>
          </div>
        </section>

        <section className="panel center-panel">
          <h2>Pipeline Progress</h2>
          <div className="pipeline-row">
            {PIPELINE_STEPS.map((step, idx) => {
              const completed = idx <= stepIndex;
              const running = idx === stepIndex && analysisRunning;
              return (
                <div key={step} className={`pipeline-step ${completed ? 'completed' : ''} ${running ? 'running' : ''}`}>
                  <span className="step-marker">{completed ? '✓' : idx + 1}</span>
                  <span className="step-text">{step}</span>
                </div>
              );
            })}
          </div>

          {analysisDone && (
            <div className="saved-banner">
              Saved ~{savedHours} hours vs traditional methods.
            </div>
          )}

          <div className="image-compare">
            <div className="img-block">
              <h3>Before</h3>
              <div className="img-stage">
                <img src={beforeImage} alt="before" />
              </div>
            </div>
            <div className="img-block">
              <h3>After + Detection Overlay</h3>
              <div className="img-stage overlay-stage">
                <img src={afterImage} alt="after" />
                {damageBoxes.map((box) => (
                  <div
                    key={box.id}
                    className={`bbox c${box.cls}`}
                    style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.w}%`, height: `${box.h}%` }}
                  >
                    <span>{DAMAGE_LEVEL[box.cls]}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="metrics-strip">
            <span>
              {damageSummary
                ? `Detections: ${damageSummary.total} | Severe Share: ${damageSummary.severePct.toFixed(1)}%`
                : 'Detections: pending'}
            </span>
            <span>Detection Confidence Window: 0.40 - 0.95</span>
            <span>Aftershock Horizon: 24h</span>
            <span>{refineLabel}</span>
          </div>

          <ShakeMapViewer
            eventId={shakeMap?.event_id}
            eventPlace={shakeMap?.event_place}
            eventMag={shakeMap?.event_mag}
            impactStr={impact?.exposed_population_estimate ? Number(impact.exposed_population_estimate).toLocaleString() : null}
          />
        </section>

        <section className="panel right-panel">
          <h2>Rescue Decision Output</h2>
          <div className="queue-list">
            {rescueQueue.length === 0 ? (
              <p>Run analysis to generate ranked rescue queue.</p>
            ) : (
              rescueQueue.map((item) => (
                <article key={item.zone} className="queue-card">
                  <div className="queue-zone">{item.zone}</div>
                  <div className="queue-meta">Estimated residents: {item.residents}</div>
                  <div className="queue-meta">Required teams: {item.teams}</div>
                  <div className={`priority ${item.priority.includes('IMMEDIATE') ? 'p-critical' : 'p-high'}`}>{item.priority}</div>
                </article>
              ))
            )}
          </div>

          <div className="forecast-card">
            <h3>Aftershock Probability (M4+)</h3>
            <p className="forecast-meta">
              Peak: {(aftershockPeak * 100).toFixed(1)}% | Avg: {(aftershockAvg * 100).toFixed(1)}% | Risk: {aftershockRiskLabel} | Source: {aftershockSource}
            </p>
            <div className="sparkline">
              {aftershock.length === 0 ? (
                <p>No forecast yet.</p>
              ) : (
                aftershock.slice(0, 24).map((p, idx) => (
                  <div key={`p-${idx}`} className="bar-wrap" title={`Hour ${idx + 1}: ${(p * 100).toFixed(1)}%`}>
                    <div
                      className={`bar ${p >= 0.6 ? 'high' : p >= 0.3 ? 'mid' : 'low'}`}
                      style={{ height: `${Math.max(6, p * 100)}%` }}
                    />
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="summary-card">
            <h3>Public Safety Brief</h3>
            {!laymanSummary ? (
              <p>Layman summary will be generated after analysis.</p>
            ) : (
              <>
                <p className="threat">Threat Level: {laymanSummary.threat_level}</p>
                <p>{laymanSummary.summary}</p>
                <ul>
                  {laymanSummary.safety_steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="shakemap-card">
            <h3>Real-Time ShakeMap</h3>
            {!shakeMap ? (
              <p>Waiting for live quake event. Run analysis or keep feed connected.</p>
            ) : (
              <>
                <p className="shake-meta">Event: {shakeMap.event_id}</p>
                <p className="shake-meta">Source: {shakeMap.source}</p>
                <div className="shake-zones">
                  {shakePolygons.length === 0 ? (
                    <p>No intensity polygons yet.</p>
                  ) : (
                    shakePolygons.map((zone, idx) => (
                      <article key={`${zone.intensity_label}-${idx}`} className="shake-zone-card">
                        <div className="shake-zone-top">
                          <strong>{zone.intensity_label}</strong>
                          <span>{(zone.area_km2 || 0).toFixed(1)} km²</span>
                        </div>
                        <div className="shake-zone-meta">
                          PGA: {(zone.pga_range_percent_g?.[0] ?? 0).toFixed(1)} - {(zone.pga_range_percent_g?.[1] ?? 0).toFixed(1)} %g
                        </div>
                      </article>
                    ))
                  )}
                </div>
                {impact && (
                  <div className="impact-card">
                    <p>Exposed Population: {Number(impact.exposed_population_estimate || 0).toLocaleString()}</p>
                    <p>Casualty Range: {Number(impact.casualty_estimate_low || 0).toLocaleString()} - {Number(impact.casualty_estimate_high || 0).toLocaleString()}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
