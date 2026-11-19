"""Figures de diagnostic et d'analyse, utilisables depuis le notebook."""
import matplotlib.pyplot as plt
import pandas as pd


def correlation_plot(stats, title):
    fig, ax = plt.subplots(figsize=(10, 5))
    usable = stats[stats.statut == "descriptif"].copy()
    if usable.empty:
        ax.text(.5, .5, "Pas assez de données simultanées\n(minimum : 30 observations sur 7 jours)",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    else:
        usable["serie"] = usable.city + " · " + usable.get("pollutant", pd.Series("", index=usable.index)) + " " + usable.get("unit", pd.Series("", index=usable.index)) + " · " + usable.x + " / " + usable.y
        # Toutes les associations restent dans le CSV ; afficher les 30 premières,
        # dans l'ordre des clés, sans sélectionner selon la force de corrélation.
        usable = usable.sort_values("serie").head(30)
        ax.barh(usable.serie, usable.rho)
        ax.axvline(0, color="black", linewidth=.7)
        ax.set_xlim(-1, 1)
        ax.set_xlabel("ρ de Spearman (association descriptive)")
        ax.tick_params(axis="y", labelsize=7)
    ax.set_title(title)
    fig.tight_layout()
    return fig


def rain_comparison(table):
    """Comparaisons par ville et créneau, sans confondre stock et activité."""
    if table.empty:
        return pd.DataFrame()
    df = table.copy()
    local = df.heure_utc.dt.tz_convert("Europe/Paris")
    df["heure_locale"] = local.dt.hour
    df["weekend"] = local.dt.dayofweek >= 5
    df = df.dropna(subset=["precipitation"])
    df["conditions"] = df.precipitation.ge(.1).map({True: "pluie ≥ 0,1 mm", False: "sec < 0,1 mm"})
    metric = "activite_par_station_heure" if "activite_par_station_heure" in df else "remplissage_moyen"
    return df.groupby(["city", "heure_locale", "weekend", "conditions"]).agg(
        moyenne=(metric, "mean"), mediane=(metric, "median"), n=(metric, "count")).reset_index().assign(indicateur=metric)
