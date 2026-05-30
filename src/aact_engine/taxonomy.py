"""Drug-class and endpoint taxonomy — lifted verbatim from
CardioOracle/curate/shared.py (the DB-connection bits omitted; we use DuckDB).

Kept identical so cohort classification is consistent across the portfolio.
"""
from __future__ import annotations

import re

DRUG_CLASS_MAP = {
    "sglt2i": {"label": "SGLT2 inhibitor", "drugs": [
        "empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin",
        "sotagliflozin", "ipragliflozin", "tofogliflozin", "luseogliflozin"]},
    "mra": {"label": "Mineralocorticoid receptor antagonist (steroidal)", "drugs": [
        "spironolactone", "eplerenone"]},
    "ns_mra": {"label": "Non-steroidal MRA", "drugs": [
        "finerenone", "esaxerenone", "apararenone", "ocedurenone"]},
    "arni": {"label": "Angiotensin receptor-neprilysin inhibitor", "drugs": [
        "sacubitril", "entresto", "sacubitril/valsartan"]},
    "arb": {"label": "Angiotensin II receptor blocker", "drugs": [
        "valsartan", "losartan", "candesartan", "irbesartan", "telmisartan",
        "olmesartan", "azilsartan"]},
    "acei": {"label": "ACE inhibitor", "drugs": [
        "enalapril", "ramipril", "lisinopril", "perindopril", "captopril",
        "quinapril", "benazepril", "fosinopril"]},
    "bb": {"label": "Beta-blocker", "drugs": [
        "carvedilol", "bisoprolol", "metoprolol", "nebivolol", "atenolol"]},
    "glp1ra": {"label": "GLP-1 receptor agonist", "drugs": [
        "semaglutide", "liraglutide", "dulaglutide", "exenatide", "albiglutide",
        "lixisenatide", "tirzepatide"]},
    "pcsk9i": {"label": "PCSK9 inhibitor", "drugs": [
        "evolocumab", "alirocumab", "inclisiran"]},
    "statin": {"label": "Statin", "drugs": [
        "atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
        "lovastatin", "fluvastatin", "pitavastatin"]},
    "anticoag": {"label": "Anticoagulant", "drugs": [
        "apixaban", "rivaroxaban", "edoxaban", "dabigatran", "warfarin"]},
    "antiplat": {"label": "Antiplatelet", "drugs": [
        "ticagrelor", "prasugrel", "clopidogrel", "aspirin", "cangrelor"]},
    "other": {"label": "Other / Unknown", "drugs": []},
}

_DOSAGE_RE = re.compile(r"\d+\s*(mg|mcg|ml|iu|units?)\b", re.IGNORECASE)


def classify_drug(intervention_name: str) -> str:
    if not intervention_name:
        return "other"
    normalised = _DOSAGE_RE.sub("", intervention_name.lower()).strip()
    for class_id, info in DRUG_CLASS_MAP.items():
        if class_id == "other":
            continue
        for drug in info["drugs"]:
            if drug in normalised:
                return class_id
    return "other"


ENDPOINT_TYPE_MAP = [
    ("mace", ["mace", "major adverse cardiovascular", "composite cardiovascular"]),
    ("hf_hosp", ["heart failure hospitalization", "hf hospitalization",
                 "worsening heart failure", "hf hospitalisation"]),
    ("cv_death", ["cardiovascular death", "cardiac death", "cv death",
                  "cardiovascular mortality"]),
    ("acm", ["all-cause mortality", "all cause mortality", "overall survival",
             "death from any cause", "all-cause death"]),
    ("renal", ["egfr", "kidney", "renal", "dialysis", "eskd",
               "doubling of creatinine", "sustained decrease"]),
    ("surrogate", ["blood pressure", "ldl", "hba1c", "nt-probnp",
                   "ejection fraction", "6-minute walk", "biomarker"]),
]


def classify_endpoint(measure_text: str) -> str:
    if not measure_text:
        return "other"
    lower = measure_text.lower()
    for endpoint_id, keywords in ENDPOINT_TYPE_MAP:
        for kw in keywords:
            if kw in lower:
                return endpoint_id
    return "other"


__all__ = ["DRUG_CLASS_MAP", "ENDPOINT_TYPE_MAP", "classify_drug", "classify_endpoint"]
