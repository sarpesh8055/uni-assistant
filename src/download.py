"""STEP 1 — Download the public source documents into data/raw/.

Run:  python -m src.download
The PDFs are public documents of Paderborn University (Electrical Systems Engineering master, v3).
They are not committed to git; this script makes the corpus reproducible.
"""
import urllib.request

from src.config import RAW_DIR

EI = "https://ei.uni-paderborn.de/fileadmin-eim/elektrotechnik"
UB = "https://digital.ub.uni-paderborn.de/hs/download/pdf"

DOCUMENTS = {
    # general provisions for all EIM master's programmes (v3, from WS 2024/25)
    "upb_eim_master_general_provisions_v3.pdf":
        f"{EI}/Formalitaeten/Ordnungen/ESE_Ordnungen/25_07_03_General_provisions_EIM_Master.pdf",
    "upb_eim_master_allgemeine_bestimmungen_v3_de.pdf": f"{UB}/7542244",              # AM 32.24, official
    # special provisions for Electrical Systems Engineering (v3)
    "upb_ese_special_provisions_v3.pdf":
        f"{EI}/Formalitaeten/Ordnungen/ESE_Ordnungen/25_08_06_Special_Provisions_ESEMA_v3.pdf",
    "upb_ese_besondere_bestimmungen_v3_de.pdf": f"{UB}/7544386",                      # AM 35.24, official
    "upb_ese_besondere_bestimmungen_v3_aenderung_2024_09_de.pdf": f"{UB}/7672852",    # AM 55.24, amendment
    "upb_ese_module_handbook_v3_ws2627.pdf":
        f"{EI}/Studium/Formalitaeten/Modulhandbuecher/WiSe26_27/ESE/"
        "Master_s_Program_Electrical_Systems_Engineering_v3__ESEMA_v3__-_2026_09_08.pdf",
    "upb_ese_preamble_v3.pdf":
        f"{EI}/Studium/Formalitaeten/Modulhandbuecher/WiSe26_27/ESE/2024_09_01_Praeambel_ESEMA_v3.pdf",
    "upb_ese_transitional_regulations_v2_to_v3_en.pdf":
        f"{EI}/Studium/Studienangebot/Electrical_Systems_Engineering/2024_09_03_Transitional_regulations_-_ESEMA_en.pdf",
    # student guides
    "upb_paul_guide_students_2026_de.pdf":
        "https://www.uni-paderborn.de/fileadmin/paul-info/Hilfe_fuer_Studierende/PAUL_Anleitung_fuer_Studierende_2026_05_27.pdf",
    "upb_introducing_paul_en.pdf":
        "https://www.eim.uni-paderborn.de/fileadmin-eim/fakultaet/Studium/Studienangebote/WelcomeWeek/2024-25/Introducing_PAUL.pdf",
    "upb_thesis_electronic_submission_de.pdf":
        "https://www.uni-paderborn.de/fileadmin/zv/3-2/allgemein/Abschlussarbeiten/Abgabe_elektronische_Abschlussarbeit_Studierende_v2.pdf",
}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in DOCUMENTS.items():
        target = RAW_DIR / name
        if target.exists():
            print(f"= {name} (already there)")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:  # university sites move files; report and continue
            print(f"✗ {name}: {e}")
            continue
        if not data.startswith(b"%PDF"):
            print(f"✗ {name}: not a PDF (the link may have moved)")
            continue
        target.write_bytes(data)
        print(f"✓ {name} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
