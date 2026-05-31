"""End-to-end UI test of the cockpit via headless Chrome (Selenium).

Assumes the server is running at http://127.0.0.1:8000. Exercises all three
methods from the GUI: pairwise MA, TSA, and the NMA-preset flow — picking
dropdowns, building, and opening each generated capsule. Asserts no severe
console errors and that each capsule's live plot renders. Saves screenshots.

Run: python tests/browser/test_cockpit_ui.py
"""
from __future__ import annotations

import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

BASE = "http://127.0.0.1:8000"
from pathlib import Path
SHOTS = Path.home() / "aact_ui_shots"
SHOTS.mkdir(exist_ok=True)


def _driver():
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1280,1600")
    o.add_argument("--no-sandbox")
    o.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=o)


def _severe(driver):
    return [l for l in driver.get_log("browser")
            if l["level"] == "SEVERE" and "favicon" not in l["message"]]


def _svg_children(driver, el_id):
    return driver.execute_script(
        f"var f=document.getElementById('{el_id}');return f?f.childElementCount:0;")


def _extract(driver, wait, preset_value, name):
    """Preset -> search -> effects table populated. Returns nothing; leaves
    card2 visible so the caller can choose a capsule type and build."""
    driver.get(BASE)
    wait.until(lambda d: "connecting" not in d.find_element(By.ID, "health").text)
    Select(driver.find_element(By.ID, "preset")).select_by_value(preset_value)
    driver.find_element(By.ID, "searchBtn").click()
    wait.until(EC.visibility_of_element_located((By.ID, "card2")))
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#effectsTable tbody tr")) > 0)
    rows = len(driver.find_elements(By.CSS_SELECTOR, "#effectsTable tbody tr"))
    print(f"  [{name}] effect rows: {rows}")
    assert rows >= 2


def build_and_open(driver, wait, kind, name, plot_id):
    print(f"\n=== {name} (kind={kind}) ===")
    _extract(driver, wait, "heart failure|acm", name)
    Select(driver.find_element(By.ID, "kind")).select_by_value(kind)
    driver.find_element(By.ID, "buildBtn").click()
    wait.until(EC.visibility_of_element_located((By.ID, "card3")))
    wait.until(lambda d: d.find_element(By.ID, "tier").text.strip() != "")
    tier = driver.find_element(By.ID, "tier").text.strip().lower()
    dl = driver.find_element(By.ID, "dl").get_attribute("href")
    print(f"  tier={tier} | {driver.find_element(By.ID,'pooledLine').text}")
    assert tier in ("bronze", "silver", "gold")
    assert not _severe(driver), f"console errors: {_severe(driver)}"

    driver.get(dl)
    wait.until(lambda d: _svg_children(d, plot_id) > 0)
    print(f"  capsule {plot_id} svg children:", _svg_children(driver, plot_id))
    if kind == "pairwise":  # funnel + leave-one-out + meta-regression plots + influence table
        wait.until(lambda d: _svg_children(d, "funnel") > 0 and _svg_children(d, "loo") > 0
                   and _svg_children(d, "metareg") > 0)
        inf_rows = len(driver.find_elements(By.CSS_SELECTOR, "#influence tbody tr"))
        print(f"  funnel={_svg_children(driver,'funnel')} loo={_svg_children(driver,'loo')} "
              f"metareg={_svg_children(driver,'metareg')} influence_rows={inf_rows}")
        assert inf_rows >= 3
    assert driver.find_element(By.ID, "tier").text.strip().lower() == tier
    assert not _severe(driver), f"capsule console errors: {_severe(driver)}"
    driver.save_screenshot(str(SHOTS / f"method_{name}.png"))
    print("  OK")


def build_nma(driver, wait):
    print("\n=== NMA preset flow ===")
    driver.get(BASE)
    wait.until(lambda d: len(Select(d.find_element(By.ID, "nmaPreset")).options) > 1)
    sel = Select(driver.find_element(By.ID, "nmaPreset"))
    sel.select_by_index(1)   # first real preset
    label = sel.first_selected_option.text
    print("  network:", label)
    driver.find_element(By.ID, "nmaBtn").click()
    wait.until(EC.visibility_of_element_located((By.ID, "nmaResult")))
    wait.until(lambda d: d.find_element(By.ID, "nmaTier").text.strip() != "")
    tier = driver.find_element(By.ID, "nmaTier").text.strip().lower()
    dl = driver.find_element(By.ID, "nmaDl").get_attribute("href")
    print(f"  tier={tier} | {driver.find_element(By.ID,'nmaLine').text}")
    assert tier in ("bronze", "silver", "gold")
    assert not _severe(driver), f"console errors: {_severe(driver)}"

    driver.get(dl)
    wait.until(lambda d: _svg_children(d, "netPlot") > 0)
    print("  capsule netPlot svg children:", _svg_children(driver, "netPlot"))
    assert not _severe(driver), f"capsule console errors: {_severe(driver)}"
    driver.save_screenshot(str(SHOTS / "method_nma.png"))
    print("  OK")


def main():
    driver = _driver()
    wait = WebDriverWait(driver, 60)
    try:
        build_and_open(driver, wait, "pairwise", "pairwise", "forest")
        build_and_open(driver, wait, "tsa", "tsa", "tsaPlot")
        build_nma(driver, wait)
        # capsule library populated after the builds above
        driver.get(BASE)
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#libTable tbody tr")) > 0)
        lib_rows = len(driver.find_elements(By.CSS_SELECTOR, "#libTable tbody tr"))
        print(f"\n=== library: {lib_rows} capsules listed ===")
        assert lib_rows >= 3
        print("\nALL UI FLOWS PASSED (pairwise + TSA + NMA + library)")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
