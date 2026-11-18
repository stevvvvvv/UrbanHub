import numpy as np
import pandas as pd

from src.batch_noaa.clean import parse_raw


def raw(**over):
    row = dict(STATION="07149099999", DATE="2024-07-01T12:00:00", LATITUDE="48.72",
               LONGITUDE="2.38", ELEVATION="89", NAME="PARIS-ORLY, FR", REPORT_TYPE="FM-15",
               WND="250,1,N,0046,1", VIS="010000,1,N,1", TMP="+0215,1", DEW="+0120,1",
               SLP="10132,1", AA1="")
    row.update(over)
    return pd.DataFrame([row])


def test_conversions_unites():
    out = parse_raw(raw()).iloc[0]
    assert out["temperature"] == 21.5
    assert out["wind_speed"] == 4.6
    assert out["wind_direction"] == 250
    assert out["visibility"] == 10.0
    assert out["pressure"] == 1013.2
    assert out["city"] == "Paris"


def test_sentinelles_et_qualite():
    out = parse_raw(raw(TMP="+9999,9", WND="999,9,V,9999,9", SLP="10132,7")).iloc[0]
    assert np.isnan(out["temperature"])
    assert np.isnan(out["wind_speed"]) and np.isnan(out["wind_direction"])
    assert np.isnan(out["pressure"])  # code qualité 7 = erroné


def test_vent_calme_et_valeur_aberrante():
    out = parse_raw(raw(WND="999,9,C,0000,1", TMP="+0999,1")).iloc[0]
    assert out["wind_speed"] == 0 and np.isnan(out["wind_direction"])
    assert np.isnan(out["temperature"])  # 99.9 °C hors bornes


def test_fusion_doublons_metar_synop():
    df = pd.concat([raw(), raw(REPORT_TYPE="FM-12", TMP="+0210,1", AA1="06,0025,9,1")])
    out = parse_raw(df)
    assert len(out) == 1
    assert out.iloc[0]["temperature"] == 21.5       # METAR prioritaire
    assert out.iloc[0]["precipitation"] == 2.5      # pluie récupérée du SYNOP
