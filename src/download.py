"""STEP 1 — Download the public source documents into data/raw/.

Run:  python -m src.download
The sources are public documents and web pages of Paderborn University (Electrical Systems
Engineering master v3, plus university-wide enrolment, fees and deadlines). They are not
committed to git; this script makes the corpus reproducible.
"""
import urllib.request

from src.config import RAW_DIR

EI = "https://ei.uni-paderborn.de/fileadmin-eim/elektrotechnik"
UB = "https://digital.ub.uni-paderborn.de/hs/download/pdf"
WWW = "https://www.uni-paderborn.de"
IO = f"{WWW}/fileadmin/international-office"

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
    # enrolment (all programmes)
    "upb_einschreibungsordnung_2026_de.pdf":
        "https://kw.uni-paderborn.de/fileadmin-kw/fakultaet/Studium/Formulare_Studium_ab_August_24/"
        "Einschreibungsordnung_der_Universitaet_Paderborn.pdf",
    "upb_io_enrolment_manual_en.pdf":
        f"{IO}/Fachstudierende/Klickanleitungen/Manual_Enrolment_in_Degree_Courses_at_Paderborn_University.pdf",
    "upb_io_short_guide_ss26_en.pdf":
        f"{IO}/Fachstudierende/Incoming_degree/Info_Studierende/Short_Guide__SS_26.040326pdf.pdf",
}

# Facts that only exist as web pages (fees, deadlines, semester dates). Saved as .html;
# ingest.py keeps the main text and treats each page as "page 1".
WEB_PAGES = {
    "upb_rueckmeldung_gebuehren_de.html": f"{WWW}/zv/3-3/studienorganisation/rueckmeldung-und-gebuehren",
    "upb_semestertermine_de.html": f"{WWW}/zv/3-3/studienorganisation/termine",
    "upb_paul_fristen_termine_de.html": f"{WWW}/studium/paul-info/fristen-und-termine",
    "upb_io_enrollment_en.html":
        f"{WWW}/en/studies/international-office/degree-students/formalities-and-services/immatrikulation",
    "upb_io_health_insurance_en.html":
        f"{WWW}/en/studies/international-office/degree-students/live-in-paderborn-and-on-campus/health-insurance",
}

# where a source can be read online (shown as a link next to citations)
SOURCE_URLS = {**DOCUMENTS, **WEB_PAGES}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCE_URLS.items():
        target = RAW_DIR / name
        if target.exists():
            print(f"= {name} (already there)")
            continue
        try:
            data = fetch(url)
        except Exception as e:  # university sites move files; report and continue
            print(f"✗ {name}: {e}")
            continue
        if name.endswith(".pdf") and not data.startswith(b"%PDF"):
            print(f"✗ {name}: not a PDF (the link may have moved)")
            continue
        if name.endswith(".html") and b"<html" not in data[:2000].lower():
            print(f"✗ {name}: not an HTML page")
            continue
        target.write_bytes(data)
        print(f"✓ {name} ({len(data) // 1024} KB)")

if __name__ == "__main__":
    main()
