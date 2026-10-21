# Receiving metric review — October 21, 2026

Follow-up: the [v3 preview extension](UPSTREAM_SPLITS.md#yac-and-receiving-first-down-extension-october-21)
now implements YAC and receiving first downs. The notes below preserve the
research checkpoint that established their definitions and coverage boundaries.

Review checkpoint, not an extension of the adapter or serving data. The existing
preview still imports only targets, catches, receiving yards and TDs. Advanced
columns remain NULL there; live rows are unchanged.

## Definitions and next integration choices

| Field | Official source/meaning | Integration direction |
|---|---|---|
| Receiving YAC | Sum of individual stat-113 yards; includes separately credited lateral recipients | Next preview addition, with field-specific historical availability |
| Receiving first downs | Reception credit plus the team's passing-first-down credit | Next preview addition; replace generic play first-down counts |
| Receiving air yards | Target credits multiplied by the play's passing air yards, including incompletions | Use only where target/air-yard coverage is supported |
| Receiving EPA | Sum of PBP EPA grouped by original receiver | Preserve original-target role; do not portray as individual lateral-yard allocation |
| EPA per target | EPA numerator and valid target denominator for the same filtered plays | Modern audit supports this mapping; historical target gap makes ratio unavailable |
| Success percentage | Not an output of the official calculator | Requires an explicit separate target-play definition if retained |

Primary definitions: [official calculator](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R)
and [stats variables](https://nflfastr.com/articles/stats_variables.html).
The upstream YAC description also states it is an unofficial measure that can
differ between sources. This review evaluates provider consistency, not an
independent official NFL YAC standard.

## Executed checks

Used installed nflfastR 6.0.0, saved hash-verified full PBP from the prior preview,
official calculations for whole season and each Down, and additional individual
reviewed plays. Scope: REG, excluding two-point attempts, 2024 and 2004. The
calculator loaded its credit source normally; research did not substitute our
Python credit implementation. All artifacts/scripts are ignored under
`data/upstream-r-trial/metric-review/` and the containing trial directory.

For every identified player, official whole-season air yards, YAC and receiving
first downs match saved weekly totals in both samples. All three also conserve
across the Down partition. Agreement on a zero from absent source records does
not establish availability.

| REG season | Air yards | YAC | Receiving first downs |
|---|---:|---:|---:|
| 2024 | 131,675 | 61,818 | 6,104 |
| 2004 | 0 (unsupported) | 0 (unsupported) | 5,524 |

## Reviewed examples

On Gibbs's two laterals, his stat-113 entries are 20 and 21 yards. The first
receivers' YAC entries are -2 and -1, respectively. Keep negative YAC: it is
not a malformed count. Gibbs gets no extra catch or target. On those plays the
official receiving-first-down credit and EPA go to the original catcher;
Gibbs receives the lateral yards and (on one play) the TD. The EPA output for
the lateral-only player on that individual play is missing, not a computed 0.

| Player / season | Air yards on all targets | YAC | Receiving first downs |
|---|---:|---:|---:|
| Gibbs 2024 | -11 | 593 | 24 |
| Jefferson 2024 | 1,682 | 487 | 62 |
| Gonzalez 2004 | Unavailable | Unavailable | 69 |

Air yards includes incomplete passes; it is not the air component of completed
receiving yards. YAC can exceed receiving yards when catches occur behind the
line of scrimmage. Do not impose `YAC <= receiving_yards` or nonnegative YAC.

## Historical availability is per field

Fresh raw credits were joined to REG nonconversion play context for all six
known target-gap seasons:

| Season | Complete-pass air records (111) | Incomplete-pass air records (112) | YAC records (113) | Target records (115) |
|---|---:|---:|---:|---:|
| 2003 | 0 | 3 | 0 | 3 |
| 2004 | 0 | 1 | 0 | 5 |
| 2005 | 0 | 0 | 0 | 0 |
| 2006 | 9,785 | 6,566 | 9,775 | 67 |
| 2007 | 10,389 | 6,597 | 10,374 | 14 |
| 2008 | 10,083 | 6,438 | 10,073 | 17 |

Targets remain incomplete throughout 2003–08. YAC is absent in 2003–05 but has
substantial records in 2006–08: do not blanket-mask YAC just because targets are
missing. Presence alone does not certify every YAC credit in those later years;
run per-player reconciliation before importing them. Receiving air-yard totals
also depend on target attribution, so passing air-yard availability from 2006
does not repair the receiver target gap.

Pre-2006 air-yard absence is consistent with upstream's explicit removal of
stray early air-yard values in its [PBP preparation code](https://github.com/nflverse/nflfastR/blob/master/R/helper_add_nflscrapr_mutations.R).
This review does not certify field availability for every other season.

## Two existing definition mismatches

First downs: our current split builder sums generic `first_down`, including
first downs awarded by penalty. In the qualified population, this differs from
official receiving first downs in 34 player/down buckets in 2024 and 28 in 2004.
Official receiving first downs exactly match fresh `first_down_pass` summed over
the existing target-play base for both samples. Reviewed rows include a short
catch followed by a roughing/unnecessary-roughness penalty that provides the
first down. Current Gonzalez Down splits total 70; the official receiving count
is 69. This is a definition correction, not lost receiving production.

EPA: published weekly totals include two-point attempts, while ordinary Down
splits exclude them. There are 69 player-season EPA differences in 2024 and 47
in 2004 before accounting for this. Adding exactly the excluded named-receiver
two-point EPA to the nonconversion calculation reconciles every numeric value
and missing value in both samples. This is an explained scope difference,
not evidence of missing ordinary-play EPA.

For qualified 2024 player/down buckets, official nonconversion receiving EPA
divided by valid targets exactly matches the fresh target-play mean EPA after
rounding to the existing four decimals. Missing values remain missing. This
supports maintaining EPA as a target-role metric; it does not give us a method
to divide a lateral play's value among players or restore historical target rates.

## Next checkpoint

Extend only the isolated preview with official YAC and receiving-first-down
counts, plus an explicit availability policy. Validate YAC separately from
targets, including 2006–08 before retaining those years. Keep EPA's original
target role and two-point scope explicit when later integrating it. Success
percentage needs a separately stated definition. Target depth/direction and
other dimensions still need their own play-context review.

No database, R producer, adapter or API changes in this checkpoint. Source DB
SHA256 remains `b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.
Ignored evidence: `findings.json`, `historical-credit-coverage.csv`, per-play
outputs, `review_receiving_metrics.R`, `check_metric_coverage.R`, and
`analyze_receiving_metrics.py`. Assertions check count reconciliation, first-down
definitions and the exact EPA scope adjustment; no full test rerun was needed.
