"""Tests for the ventilation advisor decision logic."""

from collector.advisor import (
    COMFORTABLE,
    KEEP_CLOSED,
    UNKNOWN,
    VENTILATE,
    Advisor,
)


def test_winter_dry_outside_recommends_ventilation():
    # Warm humid room, cold (absolutely dry) outside -> open the window.
    adv = Advisor().evaluate(21.0, 60.0, outdoor=(5.0, 80.0))
    assert adv.ventilation_state == VENTILATE
    assert adv.should_ventilate == 1
    assert adv.mold_risk == 1  # 60% >= mold threshold
    assert adv.outdoor_abs_humidity_gm3 < adv.indoor_abs_humidity_gm3


def test_muggy_summer_keeps_window_closed():
    # Humid room but even wetter outside -> venting would add moisture.
    adv = Advisor().evaluate(24.0, 55.0, outdoor=(28.0, 85.0))
    assert adv.ventilation_state == KEEP_CLOSED
    assert adv.should_ventilate == 0
    assert adv.mold_risk == 0


def test_comfortable_needs_no_action():
    adv = Advisor().evaluate(21.0, 45.0, outdoor=(5.0, 80.0))
    assert adv.ventilation_state == COMFORTABLE
    assert adv.should_ventilate == 0
    assert adv.mold_risk == 0


def test_no_outdoor_data_is_unknown_but_still_flags_mold():
    adv = Advisor().evaluate(21.0, 65.0, outdoor=None)
    assert adv.ventilation_state == UNKNOWN
    assert adv.should_ventilate == 0
    assert adv.mold_risk == 1
    assert adv.outdoor_abs_humidity_gm3 is None
    assert adv.indoor_abs_humidity_gm3 > 0


def test_as_reading_fields_shape():
    fields = Advisor().evaluate(21.0, 60.0, outdoor=(5.0, 80.0)).as_reading_fields()
    assert set(fields) == {
        "outdoor_temp_c", "outdoor_humidity_pct", "indoor_abs_humidity_gm3",
        "outdoor_abs_humidity_gm3", "dew_point_c", "ventilation_state",
        "should_ventilate", "mold_risk",
    }
    assert fields["ventilation_state"] == VENTILATE
    assert fields["outdoor_temp_c"] == 5.0
