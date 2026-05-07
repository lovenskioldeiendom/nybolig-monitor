"""
Konfigurasjon for hva som skal overvåkes.

MUNICIPALITIES er Akershus-kommunene du har valgt. Hver kommune har en
Finn-locationkode som brukes i søke-URL.

Du kan legge til/fjerne kommuner ved å redigere denne lista. For å finne
kode: gå til finn.no nybolig-søk, velg kommunen, kopier "location" fra URL.
"""

MUNICIPALITIES = [
    {"name": "Asker",        "finn_location": "1.20003.20046"},
    {"name": "Bærum",        "finn_location": "1.20003.20045"},
    {"name": "Nordre Follo", "finn_location": "1.20003.22104"},
    {"name": "Ås",           "finn_location": "1.20003.20041"},
]

# Bare hent prosjekter med enhetsliste (project), ikke enkeltboliger
# (projectsingle) eller bare interessemelding (planned).
PROJECT_AD_TYPE = "project"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Ven mellom hver request — vær snill mot Finn
DELAY_BETWEEN_REQUESTS_S = 4
REQUEST_TIMEOUT_S = 25
