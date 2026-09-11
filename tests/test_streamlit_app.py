from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def test_low_risk_listing_cannot_open_case(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BRANDSHIELD_DB_PATH", str(tmp_path / "low-risk.db"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    open_button = _button(app, "Open investigation case")

    assert open_button.disabled is True
    assert not app.exception


def test_high_risk_case_can_complete_human_review_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BRANDSHIELD_DB_PATH", str(tmp_path / "workflow.db"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    app.selectbox[0].select("LIST-003").run()
    assert _button(app, "Open investigation case").disabled is False

    _button(app, "Open investigation case").click().run()
    assert app.success
    assert _button(app, "Start human review")

    app.text_input[0].set_value("Foysal Emon Shanto").run()
    app.text_area[0].set_value(
        "Replica wording, an unknown seller, and an extreme discount require review."
    ).run()
    _button(app, "Start human review").click().run()

    assert _button(app, "Approve for report drafting")
    _button(app, "Approve for report drafting").click().run()

    assert _button(app, "Create takedown report draft")
    _button(app, "Create takedown report draft").click().run()

    assert any("Draft only" in warning.value for warning in app.warning)
    assert not app.exception


def test_autonomous_monitoring_cycle_surfaces_only_actionable_results(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("BRANDSHIELD_DB_PATH", str(tmp_path / "monitoring.db"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    _button(app, "Run monitoring cycle").click().run()

    assert any("completed without external actions" in item.value for item in app.success)
    assert any(metric.label == "Listings scanned" and metric.value == "4" for metric in app.metric)
    assert any(metric.label == "Reappearances" and metric.value == "1" for metric in app.metric)
    assert not app.exception
