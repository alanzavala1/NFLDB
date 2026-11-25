# Site data map

Sources and query owners for the website. Available records depend on the
published database and each source's coverage.

**Snapshot:** the database at a specific version. **Grain:** what one record
represents. Joining different grains can multiply counts unless records are
selected or aggregated first.

## Features and data owners

All rows read the snapshot unless marked online. Source paths are relative to
`api/`. Builder read functions do not prepare missing data during requests.

| Feature | Data and grain | Current owner |
|---|---|---|
| Available seasons | Played/scheduled years from `plays` and `schedules` | `services/seasons.py` |
| Schedules, results, standings | `schedules`: game; standings derived from results | `services/schedule.py`, `standings.py`, `schedule_records.py` |
| Search and biographies | `rosters`: player-season/week records | `services/search.py`, `player_profile.py` |
| Leaders and game logs | `player_game_stats`: player-game records; some services select among duplicates | `services/leaders.py`, `player_profile.py`, `team_profile.py` |
| Game details and charts | Schedules, plays, game stats and rosters | `services/game_detail.py`, `game_player_chart.py` |
| Lineups and participation | `snap_counts`, `id_map`, rosters, ratings and game stats | `services/game_lineup.py`, `player_snaps.py` |
| Game ratings | `player_game_ratings`: player-game; `team_game_ol_grades`: team-game | `game_ratings_builder.py`, `ol_grades_builder.py`, `services/game_ratings.py` |
| Receiving splits | `player_splits`, `receiving_season_totals`, `receiving_build_preparation` | `services/receiving_splits.py`, `pipeline/receiving_build.py` |
| Passing splits | `player_splits`, `passing_build_preparation` | `services/passing_splits.py`, `pipeline/passing_build.py` |
| Rushing and defensive splits | `player_splits`, `defense_splits`: entity-season-category-dimension-value | `splits_builder.py`, `def_splits_builder.py` |
| Team splits and analytics | `team_splits`, `team_season_analytics` | `team_splits_builder.py`, `team_analytics_builder.py` |
| Power rankings | `team_power_rankings`: team-season-week | `services/power_rankings.py`, `power_rankings_builder.py` |
| Similar players | `player_career_summary`, `player_comparables`: career profile and ranked neighbor | `comparables_builder.py` |
| Tracking summaries | `ngs_passing`, `ngs_rushing`, `ngs_receiving`: source-period rows aggregated by season | `services/player_tracking.py` |
| Draft, combine and awards | `draft_picks`, `combine_data`, `player_awards`, ID map | `services/player_supplemental.py`, `pipeline/awards.py` |
| Injuries and depth charts | Injury reports; latest stored daily depth snapshot | `services/team_injuries.py`, `team_depth_chart.py`, `player_supplemental.py` |
| WPA and other play-derived measures | `plays`: game-play with metric-specific conditions | `services/wpa_leaders.py`, `player_advanced.py`, `play_queries.py` |
| Live scoreboard **(online)** | Cached ESPN response; stored schedules fallback | `live/provider.py`, `live/scoreboard.py` |
| Assistant | Predefined tools and methodology text | `llm.py`, `methodology.py` |

## Upstream inputs

- **Core:** nflverse play-by-play, weekly player statistics, schedules and rosters.
  Adapters: `pipeline/sources.py`, `pipeline/context_sources.py`.
- **Supplemental:** PFR, NGS, FTN, snaps, injuries, depth charts, QBR, draft/combine
  and player IDs. Asset/coverage catalog: `pipeline/vendor_sources.py`.
- **Local reference:** awards seed in `pipeline/awards.py`.
- **Calculation:** pinned nflfastR/R exports for passing and receiving;
  see [upstream provenance](UPSTREAM_PROVENANCE.md).
- **Live:** the ESPN scoreboard adapter, outside snapshot validation.

PFR and QBR are ingested without a dedicated feature in this map. Optional
source failures can retain older data. Empty output, missing schema and an
unavailable historical field are different conditions.

## Relationships and coverage

| Relationship | Required check |
|---|---|
| Plays to games | `game_id`, game type and source coverage |
| Player-game stats to schedules | `game_id`; explicit regular/postseason scope |
| Statistics to rosters | One appropriate record per player/season before summing |
| Snap/combine IDs to players | Shared mappings and fallbacks; expose unmatched records |
| FTN context to plays | Game/play identifiers; source starts in 2022 |
| Split rows to totals | Filter category/dimension; do not sum several complete dimensions |
| Rates across periods | Sum supported numerators and matching denominators, then divide |

Targets are unavailable in 2003–2008, receiving YAC before 2006 and receiving
air yards before 2009. Other fields can remain usable. A mixed-period calculation
must not silently omit unsupported seasons. See [methodology](../api/docs/METHODOLOGY.md).
