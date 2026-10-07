export interface PatientSummary {
  engine_state: string
  engine_tone: string
  patient_id: string
  age: number
  sex: string
  icu: boolean
  n_hours: number
  state: string | null
  state_prob: number | null
  det6_risk: number | null
  abx_response: string | null
  fluid_status: string | null
  recovery: string | null
  alert_level: string
  last_hour: number
  risk_score: number | null
  risk_level: string | null
}

export interface Prediction {
  predicted_class: number
  predicted_label: string
  probability: number
  probabilities: Record<string, number>
}

export interface AlertItem {
  id: number
  patient_id: string
  hour: number
  severity: string
  category: string
  title: string
  message: string
  variable: string | null
  confidence: number | null
  acknowledged?: boolean
}

export interface TimelineEvent {
  hour: number
  type: string
  type_label?: string
  title: string
  detail: string
  severity?: string | null
  value?: string | null
  source?: string
  simulated?: boolean
  until_hour?: number
  category?: string
}

export interface Timeline {
  patient_id: string
  current_hour: number
  events: TimelineEvent[]
  counts: Record<string, number>
  event_types: Record<string, string>
}

export interface RiskComponent {
  key: string
  label: string
  available?: boolean
  points: number | null
  max_points: number
  fraction?: number | null
  value: string | null
  detail?: string
  concern?: string
}

export interface Risk {
  patient_id: string
  hour: number
  score: number | null
  level: string
  raw_score: number | null
  floor_applied: boolean
  engine_state?: string
  renormalised?: boolean
  reason?: string
  components: RiskComponent[]
  label: string
  note: string
  bands: { level: string; min: number }[]
  previous_score_6h: number | null
  delta_6h: number | null
  history: { hour: number; score: number | null; level: string }[]
  active_alert_level: string
  data_quality: { overall_score: number; level: string; caution: boolean; interpretation: string } | null
}

export interface QualityWarning {
  severity: 'warning' | 'info'
  code: string
  variable: string | null
  title: string
  message: string
  hours_ago?: number
}

export interface Quality {
  sections: Record<string, number>
  stale_labs_hours: Record<string, number>
  last_measured_hour: Record<string, number | null>
  hours_of_data: number
  overall_score: number
  level: string
  sufficient: boolean
  lab_timeliness: number
  stale_threshold_hours: number
  missing_latest: string[]
  missing_counts: Record<string, number>
  warnings: QualityWarning[]
  note: string
}

export interface RiskRow {
  patient_id: string
  age: number
  sex: string
  last_hour: number
  risk_score: number | null
  risk_level: string | null
  previous_score_6h: number | null
  delta_6h: number | null
  top_contributor: { label: string; value: string; points: number; max_points: number } | null
  components: RiskComponent[]
  engine_state: string
  recovery: string | null
  det6_risk: number | null
  alert_level: string
}

export interface SimResult {
  hour: number
  scenario: string
  hours_advanced: number
  risk: { score: number | null; level: string }
  risk_before: { score: number | null; level: string } | null
  state: { label: string; reasons: string[] }
  predictions: Record<string, Prediction>
  new_alerts: { severity: string; title: string; hour: number }[]
  steps: {
    hour: number; risk_score: number | null; risk_level: string; det6_risk: number | null
    state: string; recovery: string; new_alerts: number
  }[]
}

export interface ExplanationFactor {
  feature: string
  label: string
  contribution: number
  direction: string
  value: number | null
}

export interface Explanation {
  task: string
  predicted_label: string
  probability: number
  model: string
  factors: ExplanationFactor[]
}
