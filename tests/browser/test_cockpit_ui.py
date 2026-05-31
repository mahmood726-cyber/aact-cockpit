"""End-to-end UI test of the cockpit via headless Chrome (Selenium).

Assumes the server is running at http://127.0.0.1:8000. Drives the dropdown
flow: pick a preset -> search cohort -> build capsule -> open the capsule, and
asserts no severe console errors at each step. Saves screenshots.

Run: python tests/browser/test_cockpit_ui.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

BASE = "http://127.0.0.1:8000"
SHOTS = Path.home() / "aact_ui_shots"
SHOTS.mkdir(exist_ok=True)


def _driver():
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1280,1500")
    o.add_argument("--no-sandbox")
    o.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return webdriver.Chrome(options=o)


def _severe(driver):
    return [l for l in driver.get_log("browser")
            if l["level"] == "SEVERE" and "favicon" not in l["message"]]


def run_preset(driver, wait, preset_value, name):
    print(f"\n=== flow: {name} ({preset_value}) ===")
    driver.get(BASE)
    wait.until(lambda d: "connecting" not in d.find_element(By.ID, "health").text)
    print("  health:", driver.find_element(By.ID, "health").text)

    Select(driver.find_element(By.ID, "preset")).select_by_value(preset_value)
    summary = driver.find_element(By.ID, "summary").text
    print("  summary:", summary)
    assert "analyse" in summary.lower()
    driver.save_screenshot(str(SHOTS / f"1_form_{name}.png"))

    driver.find_element(By.ID, "searchBtn").click()
    # card2 becomes visible with rows
    wait.until(EC.visibility_of_element_located((By.ID, "card2")))
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#effectsTable tbody tr")) > 0)
    rows = len(driver.find_elements(By.CSS_SELECTOR, "#effectsTable tbody tr"))
    print("  effects summary:", driver.find_element(By.ID, "effectsSummary").text)
    print("  effect rows:", rows)
    assert rows >= 2, f"expected >=2 effect rows, got {rows}"
    driver.save_screenshot(str(SHOTS / f"2_effects_{name}.png"))

    driver.find_element(By.ID, "buildBtn").click()
    wait.until(EC.visibility_of_element_located((By.ID, "card3")))
    wait.until(lambda d: d.find_element(By.ID, "tier").text.strip() != "")
    tier = driver.find_element(By.ID, "tier").text.strip().lower()
    pooled = driver.find_element(By.ID, "pooledLine").text
    dl = driver.find_element(By.ID, "dl").get_attribute("href")
    print(f"  tier={tier} | {pooled}")
    print("  capsule:", dl)
    assert tier in ("bronze", "silver", "gold"), f"unexpected tier {tier!r}"
    driver.save_screenshot(str(SHOTS / f"3_result_{name}.png"))

    sev = _severe(driver)
    assert not sev, f"severe console errors on cockpit: {sev}"

    # open the generated capsule and verify it rendered (live forest plot drawn)
    driver.get(dl)
    wait.until(lambda d: d.find_element(By.ID, "tier").text.strip() != "")
    wait.until(lambda d: d.execute_script(
        "var f=document.getElementById('forest');return f?f.childElementCount:0;") > 0)
    n_svg = driver.execute_script("return document.getElementById('forest').childElementCount;")
    print("  forest svg children:", n_svg)
    ctier = driver.find_element(By.ID, "tier").text.strip().lower()
    pooled_line = driver.find_element(By.ID, "pooledLine").text
    print("  capsule tier:", ctier, "| pooled:", pooled_line)
    assert ctier == tier, f"capsule tier {ctier} != cockpit tier {tier}"
    csev = _severe(driver)
    assert not csev, f"severe console errors in capsule: {csev}"
    driver.save_screenshot(str(SHOTS / f"4_capsule_{name}.png"))
    print(f"  OK — screenshots in {SHOTS}")


def main():
    driver = _driver()
    wait = WebDriverWait(driver, 60)
    try:
        run_preset(driver, wait, "heart failure|acm", "hf_acm")
        run_preset(driver, wait, "type 2 diabetes|mace", "t2d_mace")
        print("\nALL UI FLOWS PASSED")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
