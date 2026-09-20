import type { DemoQuality, DemoQualityMetrics } from '../../design/demoDesign'
import './QualityPanel.css'

/** THE QUALITY PANEL (Issue #63) — makes the architectural-quality work the backend already
 * computes (Issues #17/#19/#37) visible on the plan the person is looking at.
 *
 * Every number here is READ off `quality.metrics`, never recomputed: this component does no
 * geometry or area arithmetic of its own, the same discipline `DemoPlan` already holds to for the
 * drawing. Collapsed by default under the plan — a `<details>` element, so opening it costs no
 * extra state or wiring — and entirely absent when the backend has not attached metrics (a
 * payload from before Issue #17, or a design that predates it). */

interface Metric {
  key: keyof DemoQualityMetrics
  label: string
  meaning: string
  format: (value: DemoQualityMetrics) => string | null
  corpusMedian: (value: DemoQualityMetrics) => number | null | undefined
}

const PERCENT = (n: number) => `${(n * 100).toFixed(0)}%`
const RATIO = (n: number) => n.toFixed(2)

const METRICS: Metric[] = [
  {
    key: 'm1_habitable_aspect_median',
    label: 'M1 — יחס צורת חדרים',
    meaning: 'יחס אורך/רוחב של חדרי המגורים (חציון ומקסימום) — ככל שקרוב יותר ל-1, החדר קרוב יותר לריבוע',
    format: (m) =>
      m.m1_habitable_aspect_median === null ? null
        : `חציון ${RATIO(m.m1_habitable_aspect_median)}${m.m1_habitable_aspect_max !== null ? `, מקסימום ${RATIO(m.m1_habitable_aspect_max)}` : ''}`,
    corpusMedian: () => null,
  },
  {
    key: 'm2_habitable_on_envelope_ratio',
    label: 'M2 — נגיעה במעטפת',
    meaning: 'אחוז חדרי המגורים הנוגעים בקיר החיצוני של הבניין',
    format: (m) => (m.m2_habitable_on_envelope_ratio === null ? null : PERCENT(m.m2_habitable_on_envelope_ratio)),
    corpusMedian: () => null,
  },
  {
    key: 'm3_circulation_share',
    label: 'M3 — חלק התנועה',
    meaning: 'אחוז שטח המסדרונות מתוך סך שטח החדרים',
    format: (m) => PERCENT(m.m3_circulation_share),
    corpusMedian: (m) => m.corpus_median?.m3_circulation_share_median,
  },
  {
    key: 'm4_hall_aspect_median',
    label: 'M4 — צורת המסדרון',
    meaning: 'כמה דלתות נפתחות אל המסדרון, ויחס האורך/רוחב שלו עצמו',
    format: (m) =>
      m.m4_hall_aspect_median === null ? null
        : `יחס ${RATIO(m.m4_hall_aspect_median)}${m.m4_hall_door_count !== null ? `, ${m.m4_hall_door_count} דלתות` : ''}`,
    corpusMedian: (m) => m.corpus_median?.m4_hall_aspect_median,
  },
  {
    key: 'm5_wet_adjacency_ratio',
    label: 'M5 — סמיכות חדרים רטובים',
    meaning: 'אחוז חדרי הרחצה/שירותים החולקים קיר עם חדר רטוב אחר, מטבח או חדר כביסה',
    format: (m) => (m.m5_wet_adjacency_ratio === null ? null : PERCENT(m.m5_wet_adjacency_ratio)),
    corpusMedian: (m) => m.corpus_median?.m5_wet_adjacency_share,
  },
  {
    key: 'm6_public_zone_contiguous',
    label: 'M6 — רציפות האזור הציבורי',
    meaning: 'האם הסלון, פינת האוכל והמטבח יוצרים מרחב אחד רציף',
    format: (m) => (m.m6_public_zone_contiguous === null ? null : (m.m6_public_zone_contiguous ? 'כן' : 'לא')),
    corpusMedian: (m) => m.corpus_median?.m6_public_contiguous_share,
  },
]

function MetricRow({ metric, metrics }: { metric: Metric; metrics: DemoQualityMetrics }) {
  const value = metric.format(metrics)
  if (value === null) return null
  const median = metric.corpusMedian(metrics)
  return (
    <li className="quality-metric-row">
      <span className="quality-metric-label" title={metric.meaning}>{metric.label}</span>
      <span className="quality-metric-value">{value}</span>
      {median !== null && median !== undefined ? (
        <span className="quality-metric-median">חציון קורפוס: {
          metric.key === 'm4_hall_aspect_median' ? RATIO(median) : PERCENT(median)
        }</span>
      ) : null}
    </li>
  )
}

function QualityPanel({ quality }: { quality: DemoQuality | null | undefined }) {
  const metrics = quality?.metrics
  if (!metrics) return null

  return (
    <details className="quality-panel">
      <summary className="quality-panel-summary">מדדי איכות אדריכלית</summary>
      <ul className="quality-metric-list">
        {METRICS.map((metric) => (
          <MetricRow key={metric.key} metric={metric} metrics={metrics} />
        ))}
      </ul>
      <dl className="quality-extra-facts">
        <div>
          <dt>שטח מת</dt>
          <dd>{metrics.dead_space_m2.toFixed(2)} מ״ר</dd>
        </div>
        <div>
          <dt>תנועה מבוזבזת</dt>
          <dd>{PERCENT(metrics.wasted_circulation_share)}</dd>
        </div>
      </dl>
    </details>
  )
}

export default QualityPanel
