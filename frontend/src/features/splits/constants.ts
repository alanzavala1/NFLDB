

export const CAREER_SEASON = 0

// sentinel: aggregate across all seasons

// Dimension that fully partitions every play (no NULL bucket) — summing all
// its values yields the "Overall" (unfiltered) row. `down` is set on every
// scrimmage pass/run play, so it covers all of them.
export const OVERALL_DIM = 'down'
