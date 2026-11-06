"""Independent native season totals with the same per-play metric checks."""
from pipeline.passing_down import MAPPING, UNVERIFIED
from pipeline.passing_metrics import apply_passing_metrics
from splits_core import PLAYER_COLUMNS


def prepare_passing_summary(whole, context, credits, season, qualified):
    """Whole counts were verified before admission by every partition adapter.

    Recheck detailed credits and model populations on the whole play set so a
    missing Down/context label cannot silently remove production from a summary.
    """
    source = whole.assign(split_value="all")
    selected = source.loc[source.player_id.isin(qualified)].rename(columns=MAPPING).copy()
    selected["category"], selected["split_dim"], selected["sort_order"] = "passing", "overall", 1
    for field in UNVERIFIED:
        selected[field] = None
    rows, metrics = apply_passing_metrics(selected[list(PLAYER_COLUMNS)], source, context, credits,
                                         season, dimension="overall")
    values = rows.sort_values("player_id").reset_index(drop=True).astype(object)
    return {"format_version": 1, "rows": values.where(values.notna(), None).to_dict(orient="records"),
            "metric_availability": metrics}
