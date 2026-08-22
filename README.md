# PhD Scraper 🎓

Outil personnel de veille des opportunités doctorales rémunérées en **Allemagne**, **France** et dans le reste de l'Europe, avec notification **Telegram** automatique.

Domaines ciblés : Cloud Computing · Distributed Systems · Systems Research · Infrastructure · Kubernetes · Edge Computing.

---

## Architecture

```
phd-scraper/
  config/
    keywords.yaml       # mots-clés include/exclude
    sources.yaml        # scrapers actifs
  scraper/
    models.py           # Pydantic Offer model
    db.py               # SQLite — insert, dedup, status
    filters.py          # filtrage par mots-clés
    notifier.py         # envoi Telegram
    base.py             # BaseScraper abstrait
    run.py              # point d'entrée CLI
    sources/            # un fichier par source
      euraxess.py       # ★ source prioritaire multi-pays
      inria.py          # France — portail PhD doctorants
      daad_phdgermany.py
      cnrs.py
      fraunhofer.py
      max_planck.py
      adum.py
      campusfrance.py
      lab_tum_dse.py
      lab_tuda_systems.py
      lab_rwth_comsys.py
  tests/
    test_filters.py
    test_db.py
    test_sources/
      test_euraxess.py
      test_inria.py
      test_daad.py
      test_cnrs.py
      test_fraunhofer.py
      test_max_planck.py
      test_adum.py
      test_campusfrance.py
      test_lab_tum_dse.py
      test_lab_tuda_systems.py
      test_lab_rwth_comsys.py
```

---

## Installation

```bash
# 1. Cloner le repo
git clone <repo> phd-scraper
cd phd-scraper

# 2. Créer un virtualenv
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer l'environnement
cp .env.example .env
# Éditer .env avec :
#   TELEGRAM_BOT_TOKEN=<token du bot @BotFather>
#   TELEGRAM_CHAT_ID=<ton chat ID personnel>
#   DB_PATH=data/offers.db
#   USER_AGENT=PIO-PhD-Scraper/1.0 (contact: ton-email@example.com)
```

---

## Configuration Telegram

1. Créer un bot via [@BotFather](https://t.me/BotFather) → `/newbot` → noter le token
2. Ouvrir une conversation avec ton bot, puis récupérer ton chat ID via :
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Renseigner `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env`
4. Tester la connexion :
   ```bash
   python -m scraper.run test-notify
   ```

---

## Utilisation

```bash
# Lancer un cycle complet (scraping → filtrage → dedup → Telegram)
python -m scraper.run scan

# Lister les offres non encore notifiées
python -m scraper.run list --new

# Lister toutes les offres stockées
python -m scraper.run list

# Marquer une offre manuellement
python -m scraper.run mark 42 applied
python -m scraper.run mark 17 ignored

# Test de notification Telegram
python -m scraper.run test-notify
```

---

## Déploiement CI/CD automatique (GitHub Actions ➔ Contabo VPS)

Le projet contient un workflow GitHub Actions prêt à l'emploi (`.github/workflows/deploy.yml`) qui :
1. **Exécute la suite de tests unitaires (pytest)** à chaque commit/PR.
2. **Construit et publie l'image Docker** sur GitHub Container Registry (`ghcr.io`).
3. **Se connecte en SSH à votre VPS Contabo** pour déployer l'image et planifier l'exécution quotidienne automatique (07:00 UTC).

### Configuration des Secrets GitHub

Dans votre dépôt GitHub, allez dans **Settings > Secrets and variables > Actions** et ajoutez :

| Secret | Description / Exemple |
|--------|-----------------------|
| `VPS_HOST` | Adresse IP de votre VPS Contabo (ex: `194.163.xxx.xxx`) |
| `VPS_USER` | Utilisateur SSH (ex: `root` ou `ubuntu`) |
| `VPS_SSH_KEY` | Clé privée SSH pour vous connecter au VPS (`~/.ssh/id_rsa`) |
| `TELEGRAM_BOT_TOKEN` | Token de votre bot Telegram |
| `TELEGRAM_CHAT_ID` | Votre Chat ID Telegram personnel |
| `VPS_PORT` | *(Optionnel)* Port SSH (défaut : `22`) |

Dès que vous poussez sur `main`, GitHub Actions déploie automatiquement la dernière version du scraper sur votre VPS Contabo.

---

## Déploiement manuel sur VPS Contabo

### Option 1 : Déploiement via script 1-Click

Sur votre VPS Contabo (Ubuntu / Debian) :

```bash
git clone <repo> phd-scraper
cd phd-scraper
./deploy.sh
```

### Option 2 : Déploiement via Docker Compose

```bash
# 1. Configurer l'environnement
cp .env.example .env
nano .env

# 2. Lancer un scan manuel via Docker
docker compose run --rm phd-scraper scan
```


### Option 3 : Timer Systemd (Natif Linux)

```bash
sudo cp systemd/phd-scraper.service /etc/systemd/system/
sudo cp systemd/phd-scraper.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now phd-scraper.timer
```

Pour vérifier le statut et les prochains déclenchements :
```bash
sudo systemctl status phd-scraper.timer
sudo systemctl list-timers | grep phd-scraper
```

Les logs quotidiens sont écrits dans `logs/scraper_YYYY-MM-DD.log`.

---

## Tests

```bash
# Lancer tous les tests (sans réseau — fixtures statiques uniquement)
pytest

# Avec rapport de couverture
pytest --cov=scraper --cov-report=term-missing
```

---

## Ajouter une nouvelle source

1. Créer `scraper/sources/ma_source.py` héritant de `BaseScraper`
2. Implémenter `fetch()` et `parse()` 
3. Ajouter l'entrée dans `config/sources.yaml`
4. Capturer une fixture HTML statique dans `tests/fixtures/`
5. Créer `tests/test_sources/test_ma_source.py` qui teste `parse()` sur la fixture

---

## Sources couvertes

| Source | Pays | Type |
|--------|------|------|
| EURAXESS | 🇪🇺 Multi-pays | Portail officiel EU |
| Inria | 🇫🇷 France | Portail carrières |
| CNRS | 🇫🇷 France | Portail emploi |
| ADUM | 🇫🇷 France | Écoles doctorales |
| CampusFrance | 🇫🇷 France | Portail doctorat |
| DAAD PhDGermany | 🇩🇪 Allemagne | Portail officiel |
| Fraunhofer | 🇩🇪 Allemagne | Portail centralisé |
| Max Planck | 🇩🇪 Allemagne | Portail centralisé |
| TUM DSE (Bhatotia) | 🇩🇪 Munich | Labo individuel |
| Systems@TUDa (Istvan) | 🇩🇪 Darmstadt | Labo individuel |
| RWTH COMSYS (Wehrle) | 🇩🇪 Aachen | Labo individuel |

---

## Contraintes éthiques

- ✅ User-Agent honnête et identifiable
- ✅ Vérification `robots.txt` avant chaque scraper
- ✅ Délai ≥ 1.5s entre requêtes successives sur un même domaine
- ✅ Timeout 12s + 2 tentatives max
- ✅ Aucun contournement d'authentification ou CAPTCHA
- ✅ Volume très faible (quelques pages/jour par source)
