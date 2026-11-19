"""Cas contrôlés : dates décalées, doublons, trous de collecte, unités."""
import numpy as np
import pandas as pd
import pytest
from src.analysis_cross.prepare import bike_hourly, noaa_daily, pollution_tables, join, load_bikes
from src.analysis_cross.run import correlations, run
from src.analysis_cross.weather import parse_response


def bike_rows():
    return pd.DataFrame([dict(city="Paris", network="velib", station_id=str(s),
        collected_at=f"2025-01-01T00:{minute}:00Z", bikes_available=b, capacity=10)
        for minute, b in [("00", 4), ("05", 6), ("30", 9)] for s in range(2)])


def test_bike_stock_not_summed_across_collections_and_gap_excluded():
    df = bike_rows()
    out = bike_hourly(pd.concat([df, df.iloc[:1]])).iloc[0]
    assert out.velos_disponibles == pytest.approx((8 + 12 + 18) / 3)
    assert out.movement == 4  # le trou de 25 min ne compte pas
    assert out.activite_par_station_heure == pytest.approx(24)
    assert out.collectes == 3


def test_first_snapshot_not_zero_activity():
    out = bike_hourly(bike_rows().iloc[:2]).iloc[0]
    assert np.isnan(out.activite_par_station_heure)


def test_paris_two_noaa_stations_do_not_multiply_pollution():
    noaa = pd.DataFrame(dict(city=["Paris"]*2, station_id=["a", "b"],
        date=["2024-01-01"]*2, t_mean=[10, 12], wind_mean=[2, 4]))
    right = noaa_daily(noaa)
    left = pd.DataFrame(dict(city=["Paris"], date=pd.to_datetime(["2024-01-01"]), pollution=[20]))
    out = join(left, right, ["city", "date"])
    assert len(out) == 1 and out.t_mean.iloc[0] == 11
    left["date"] += pd.Timedelta(days=366)
    assert join(left, right, ["city", "date"]).empty


def pollution_rows():
    return pd.DataFrame(dict(city="PARIS", sensor_id=1, pollutant="no2", unit="µg/m³", value=20,
        timestamp=pd.date_range("2024-01-01T00:00Z", periods=24, freq="h")))


def test_pollution_local_date_units_duplicates_and_coverage():
    df = pollution_rows()
    other = df.assign(sensor_id=2, unit="ppb", value=10)
    hourly, daily = pollution_tables(pd.concat([df, df, other]))
    assert len(hourly) == 48
    assert set(daily.unit) == {"µg/m³", "ppb"}
    assert len(daily) == 2  # le 2 janvier n'a qu'une heure, donc est exclu
    assert set(daily.date) == {pd.Timestamp("2024-01-01")}
    assert pollution_tables(df.iloc[:3])[1].empty


def test_correlations_refuse_short_duration_and_constant():
    dates = pd.date_range("2024-01-01", periods=31, freq="h", tz="UTC")
    df = pd.DataFrame(dict(city="Paris", heure_utc=dates, x=range(31), y=range(31)))
    result = correlations(df, ["city"], ["x"], ["y"], "heure_utc").iloc[0]
    assert np.isnan(result.rho) and result.statut == "échantillon insuffisant"
    df.heure_utc = pd.date_range("2024-01-01", periods=31, freq="D", tz="UTC")
    assert correlations(df, ["city"], ["x"], ["y"], "heure_utc").rho.iloc[0] == pytest.approx(1)
    df.y = 1
    assert correlations(df, ["city"], ["x"], ["y"], "heure_utc").statut.iloc[0] == "variable constante"


def test_absent_inputs_produce_diagnostic(tmp_path):
    tables, stats, cov, manifest = run(tmp_path / "processed", tmp_path / "out", tmp_path / "reports")
    assert all(t.empty for t in tables.values())
    assert (tmp_path / "reports" / "synthese.md").exists()
    assert manifest["lignes_jointes"]["trois_flux"] == 0


def test_full_pipeline_with_simulated_inputs(tmp_path):
    p = tmp_path / "processed"
    (p / "citybikes").mkdir(parents=True)
    (p / "openmeteo").mkdir()
    (p / "openaq").mkdir()
    bike_rows().to_parquet(p / "citybikes/dt=2025-01-01.parquet")
    pd.DataFrame(dict(city=["Paris"], heure_utc=pd.to_datetime(["2025-01-01T00:00Z"]),
        temperature=[10], wind_speed=[2], precipitation=[0])).to_parquet(p / "openmeteo/weather_hourly.parquet")
    pollution_rows().assign(timestamp=lambda d: d.timestamp + pd.DateOffset(years=1)).to_parquet(p / "openaq/pollution_clean.parquet")
    pd.DataFrame(dict(city=["Paris"], station_id=["a"], date=pd.to_datetime(["2025-01-01"]),
        t_mean=[10], wind_mean=[2])).to_parquet(p / "noaa_daily.parquet")
    tables, _, _, _ = run(p, tmp_path / "out", tmp_path / "reports")
    assert len(tables["meteo_velos"]) == len(tables["meteo_pollution"]) == len(tables["trois_flux"]) == 1


def test_old_bike_export_does_not_use_inflated_stocks(tmp_path):
    pd.DataFrame(dict(city=["Paris"], heure_utc=["2025-01-01T00:00Z"],
        velos_disponibles=[10000], mouvements=[5], remplissage_moyen=[.5])).to_parquet(tmp_path / "citybikes_hourly.parquet")
    df, source = load_bikes(tmp_path)
    assert "velos_disponibles" not in df and "mouvements" not in df
    assert df.remplissage_moyen.iloc[0] == .5


def test_weather_parser_checks_units():
    payload = {"hourly_units": {"temperature_2m":"°C", "precipitation":"mm", "wind_speed_10m":"m/s", "relative_humidity_2m":"%"},
        "hourly": {"time":["2025-01-01T00:00"], "temperature_2m":[10], "precipitation":[0], "wind_speed_10m":[2], "relative_humidity_2m":[60]}}
    assert str(parse_response(payload, "Paris").heure_utc.dt.tz) == "UTC"
    payload["hourly_units"]["wind_speed_10m"] = "km/h"
    with pytest.raises(ValueError):
        parse_response(payload, "Paris")
